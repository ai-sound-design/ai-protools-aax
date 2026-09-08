#!/usr/bin/env python3
"""
Import orphaned BBC Sound Archive files that exist on disk but not in the database.

These are WAV files that were downloaded but don't have corresponding CSV entries.
The script will:
1. Scan all WAV files in the sounds directory
2. Identify files not already in the database
3. Parse metadata from filenames
4. Measure audio duration
5. Add new entries to the database
"""

import sys
import wave
import os
from pathlib import Path
from typing import Tuple, Optional
import psycopg2

# Configuration
SOUNDS_DIR = Path("/mnt/data/BBCSoundDownloader/sounds")
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,  # Docker exposed port
    "database": "bbc_sounds",
    "user": "bbc_user",
    "password": os.getenv("BBC_DB_PASSWORD", "change_me")
}


def get_wav_duration(file_path: Path) -> Optional[float]:
    """
    Get duration of WAV file in seconds.
    
    Args:
        file_path: Path to WAV file
        
    Returns:
        Duration in seconds or None if file cannot be read
    """
    try:
        with wave.open(str(file_path), 'r') as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            duration = frames / float(rate)
            return duration
    except Exception as e:
        print(f"Warning: Could not read {file_path.name}: {e}")
        return None


def parse_filename(filename: str) -> Optional[Tuple[str, str]]:
    """
    Parse orphaned sound filename to extract description and location.
    
    Expected format: "Description..ID.wav" (note double dots)
    Example: "100 men, prolonged cheer..07035068.wav"
    
    Args:
        filename: The WAV filename
        
    Returns:
        Tuple of (description, location) or None if parsing fails
    """
    if ".." not in filename:
        return None
        
    try:
        # Split on last occurrence of ".."
        parts = filename.rsplit("..", 1)
        if len(parts) != 2:
            return None
            
        description = parts[0].strip()
        location = parts[1].strip()
        
        # Validate location format (should be like "07035068.wav")
        if not location.endswith(".wav"):
            return None
            
        return (description, location)
    except Exception as e:
        print(f"Warning: Could not parse filename '{filename}': {e}")
        return None


def import_orphaned_sounds() -> Tuple[int, int]:
    """
    Find and import orphaned sound files.
    
    Returns:
        Tuple of (files_imported, files_skipped)
    """
    if not SOUNDS_DIR.exists():
        print(f"Error: Sounds directory not found: {SOUNDS_DIR}")
        sys.exit(1)
    
    print("Orphaned BBC Sound Archive Importer")
    print("=" * 60)
    print(f"Scanning: {SOUNDS_DIR}")
    print()
    
    # Connect to database
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
    except Exception as e:
        print(f"Database connection error: {e}")
        sys.exit(1)
    
    # Get all existing locations from database
    print("Loading existing database entries...")
    cursor.execute("SELECT location FROM bbc_sounds")
    db_locations = {row[0] for row in cursor.fetchall()}
    print(f"Found {len(db_locations)} entries in database")
    print()
    
    # Find all WAV files
    print("Scanning filesystem for WAV files...")
    all_wav_files = list(SOUNDS_DIR.rglob("*.wav"))
    print(f"Found {len(all_wav_files)} WAV files on disk")
    print()
    
    # Process orphaned files
    files_imported = 0
    files_skipped = 0
    files_error = 0
    batch_data = []
    batch_size = 100
    
    print("Identifying and processing orphaned files...")
    print()
    
    for wav_file in all_wav_files:
        filename = wav_file.name
        
        # Parse filename to get location
        parsed = parse_filename(filename)
        if not parsed:
            # Try simple format: just extract the ID.wav part
            if filename.endswith(".wav"):
                # Maybe it's already in DB with this exact filename
                if filename in db_locations:
                    files_skipped += 1
                    continue
                else:
                    # Unknown format, skip
                    files_error += 1
                    continue
            else:
                files_error += 1
                continue
        
        description, location = parsed
        
        # Check if already in database
        if location in db_locations:
            files_skipped += 1
            continue
        
        # Get category from directory name
        cdname = wav_file.parent.name
        category = cdname  # Use directory name as category
        
        # Measure duration
        duration_seconds = get_wav_duration(wav_file)
        if duration_seconds is None:
            files_error += 1
            continue
        
        # Add to batch
        batch_data.append((
            location,
            description,
            cdname,
            None,  # cdnumber - unknown
            category,
            None,  # tracknum - unknown
            duration_seconds,
            str(wav_file),
            True  # file_exists
        ))
        
        # Insert batch when full
        if len(batch_data) >= batch_size:
            try:
                cursor.executemany(
                    """
                    INSERT INTO bbc_sounds 
                    (location, description, cdname, cdnumber, category, tracknum, duration_seconds, file_path, file_exists)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (location) DO NOTHING
                    """,
                    batch_data
                )
                conn.commit()
                files_imported += len(batch_data)
                print(f"Imported {files_imported} orphaned files... ({files_skipped} already in DB, {files_error} errors)")
                batch_data = []
            except Exception as e:
                print(f"Error inserting batch: {e}")
                conn.rollback()
                batch_data = []
    
    # Insert remaining records
    if batch_data:
        try:
            cursor.executemany(
                """
                INSERT INTO bbc_sounds 
                (location, description, cdname, cdnumber, category, tracknum, duration_seconds, file_path, file_exists)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (location) DO NOTHING
                """,
                batch_data
            )
            conn.commit()
            files_imported += len(batch_data)
        except Exception as e:
            print(f"Error inserting final batch: {e}")
            conn.rollback()
    
    cursor.close()
    conn.close()
    
    print()
    print("=" * 60)
    print("Import Complete!")
    print("=" * 60)
    print(f"Orphaned files imported: {files_imported}")
    print(f"Files already in DB: {files_skipped}")
    print(f"Files with errors: {files_error}")
    print()
    
    return files_imported, files_skipped


if __name__ == "__main__":
    try:
        imported, skipped = import_orphaned_sounds()
        
        # Print final database stats
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE file_exists = true) as exists,
                COUNT(*) FILTER (WHERE file_exists = false) as missing
            FROM bbc_sounds
        """)
        total, exists, missing = cursor.fetchone()
        cursor.close()
        conn.close()
        
        print("Final Database Statistics:")
        print(f"  Total entries: {total}")
        print(f"  Files exist: {exists}")
        print(f"  Files missing: {missing}")
        
    except KeyboardInterrupt:
        print("\n\nImport interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        sys.exit(1)
