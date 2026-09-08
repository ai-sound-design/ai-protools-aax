#!/usr/bin/env python3
"""
Import BBC Sound Archive metadata from CSV into PostgreSQL database.

Reads BBCSoundEffects_max30s.csv and imports all sound effect metadata,
checking for file existence and calculating statistics.
"""

import csv
import psycopg2
from pathlib import Path
from typing import Dict, Tuple
import sys
import os

# Database connection parameters
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'bbc_sounds',
    'user': 'bbc_user',
    'password': os.getenv('BBC_DB_PASSWORD', 'change_me')
}

# Paths
CSV_FILE = Path('/mnt/data/BBCSoundDownloader/BBCSoundEffects_max30s.csv')
SOUNDS_DIR = Path('/mnt/data/BBCSoundDownloader/sounds')


def parse_duration(duration_str: str) -> float:
    """
    Parse duration from CSV (format: seconds as integer, MM:SS or HH:MM:SS) to seconds.
    
    Args:
        duration_str: Duration string like "17", "00:30" or "01:23:45"
    
    Returns:
        Duration in seconds as float
    """
    try:
        duration_str = duration_str.strip()
        
        # Check if it contains colon (time format)
        if ':' in duration_str:
            parts = duration_str.split(':')
            if len(parts) == 2:
                # MM:SS format
                minutes, seconds = map(int, parts)
                return minutes * 60 + seconds
            elif len(parts) == 3:
                # HH:MM:SS format
                hours, minutes, seconds = map(int, parts)
                return hours * 3600 + minutes * 60 + seconds
        else:
            # Plain integer seconds
            return float(duration_str)
            
        return 0.0
    except (ValueError, AttributeError) as e:
        print(f"Warning: Could not parse duration '{duration_str}': {e}")
        return 0.0


def construct_file_path(cdname: str, description: str, location: str) -> Path:
    """
    Construct the expected file path for a sound effect.
    
    Args:
        cdname: CD name (directory)
        description: Sound description (filename without extension)
        location: File extension (wav, flac, etc.)
    
    Returns:
        Path object to the expected file location
    """
    return SOUNDS_DIR / cdname / f"{description}.{location}"


def import_sounds() -> Tuple[int, int, int]:
    """
    Import BBC Sound Archive metadata from CSV into PostgreSQL.
    
    Returns:
        Tuple of (total_imported, files_found, files_missing)
    """
    if not CSV_FILE.exists():
        print(f"Error: CSV file not found: {CSV_FILE}")
        sys.exit(1)
    
    print(f"Reading CSV: {CSV_FILE}")
    print(f"Checking files in: {SOUNDS_DIR}")
    print()
    
    # Connect to database
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
    except psycopg2.Error as e:
        print(f"Error: Could not connect to database: {e}")
        sys.exit(1)
    
    # Read CSV and import data
    total_imported = 0
    files_found = 0
    files_missing = 0
    batch_size = 100
    batch_data = []
    
    try:
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            # CSV format: location,description,secs,category,CDNumber,CDName,tracknum
            reader = csv.DictReader(f)
            
            for row in reader:
                location = row['location'].strip()
                description = row['description'].strip()
                cdname = row['CDName'].strip()
                cdnumber = row.get('CDNumber', '').strip()
                category = row.get('category', '').strip()
                tracknum_str = row.get('tracknum', '').strip()
                duration_str = row['secs'].strip()
                
                # Parse tracknum (may be empty)
                try:
                    tracknum = int(tracknum_str) if tracknum_str else None
                except ValueError:
                    tracknum = None
                
                # Parse duration
                duration_seconds = parse_duration(duration_str)
                
                # Construct and check file path
                file_path = construct_file_path(cdname, description, location)
                
                # Check if file exists (handle OSError for too-long filenames)
                try:
                    file_exists = file_path.exists()
                except OSError as e:
                    # Filename too long or other OS error
                    file_exists = False
                
                if file_exists:
                    files_found += 1
                else:
                    files_missing += 1
                
                # Add to batch
                batch_data.append((
                    location,
                    description,
                    cdname,
                    cdnumber if cdnumber else None,
                    category if category else None,
                    tracknum,
                    duration_seconds,
                    str(file_path),
                    file_exists
                ))
                
                # Insert batch when full
                if len(batch_data) >= batch_size:
                    cursor.executemany(
                        """
                        INSERT INTO bbc_sounds 
                        (location, description, cdname, cdnumber, category, tracknum, duration_seconds, file_path, file_exists)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        batch_data
                    )
                    conn.commit()
                    total_imported += len(batch_data)
                    print(f"Imported {total_imported} sounds... ({files_found} found, {files_missing} missing)")
                    batch_data = []
            
            # Insert remaining records
            if batch_data:
                cursor.executemany(
                    """
                    INSERT INTO bbc_sounds 
                    (location, description, cdname, cdnumber, category, tracknum, duration_seconds, file_path, file_exists)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    batch_data
                )
                conn.commit()
                total_imported += len(batch_data)
        
        print()
        print("=" * 60)
        print("Import Complete!")
        print("=" * 60)
        print(f"Total sounds imported: {total_imported}")
        print(f"Files found: {files_found} ({files_found/total_imported*100:.1f}%)")
        print(f"Files missing: {files_missing} ({files_missing/total_imported*100:.1f}%)")
        print()
        
        # Query statistics from database
        cursor.execute("SELECT * FROM sound_stats")
        stats = cursor.fetchone()
        if stats:
            print("Database Statistics:")
            print(f"  Total sounds: {stats[0]}")
            print(f"  Available sounds: {stats[1]}")
            print(f"  Missing sounds: {stats[2]}")
            print(f"  Total hours available: {stats[3]:.2f}")
            print(f"  Unique categories: {stats[4]}")
            print(f"  Average duration: {stats[5]:.1f} seconds")
            print()
        
        # Show top categories
        cursor.execute("SELECT * FROM category_stats ORDER BY available_sounds DESC LIMIT 10")
        categories = cursor.fetchall()
        if categories:
            print("Top 10 Categories by Available Sounds:")
            for cat in categories:
                cdname, total, available, total_duration, avg_duration = cat
                total_hours = total_duration / 3600 if total_duration else 0
                print(f"  {cdname}: {total} sounds ({available} available, {total_hours:.1f} hours)")
            print()
        
    except Exception as e:
        print(f"Error during import: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
    
    return total_imported, files_found, files_missing


if __name__ == '__main__':
    print("BBC Sound Archive Importer")
    print("=" * 60)
    print()
    
    try:
        import_sounds()
        print("Import successful!")
    except KeyboardInterrupt:
        print("\nImport cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)
