#!/usr/bin/env python3
"""
Fix file paths for BBC Sound Archive entries that exist on disk but have
incorrect file_path in the database.

The import script constructed paths based on CSV cdname, but some files
are in different directory structures. This script scans the actual filesystem
and updates the database with correct paths.
"""

import sys
import re
import os
from pathlib import Path
import psycopg2

# Configuration
SOUNDS_DIR = Path("/mnt/data/BBCSoundDownloader/sounds")
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "bbc_sounds",
    "user": "bbc_user",
    "password": os.getenv("BBC_DB_PASSWORD", "change_me")
}


def extract_location_from_filename(filename: str) -> str:
    """
    Extract the location (ID.wav) from a filename.
    
    Examples:
        "Description.07035068.wav" -> "07035068.wav"
        "Description..07035068.wav" -> "07035068.wav"
    
    Args:
        filename: The WAV filename
        
    Returns:
        The location part (8-digit ID + .wav)
    """
    # Pattern: 8 digits followed by .wav at the end
    match = re.search(r'\.?(\d{8}\.wav)$', filename)
    if match:
        return match.group(1)
    return filename  # fallback: use entire filename


def fix_file_paths():
    """
    Scan filesystem and update database with correct file paths.
    """
    if not SOUNDS_DIR.exists():
        print(f"Error: Sounds directory not found: {SOUNDS_DIR}")
        sys.exit(1)
    
    print("BBC Sound Archive - File Path Fixer")
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
    
    # Get all entries that don't have existing files
    print("Loading database entries without existing files...")
    cursor.execute("""
        SELECT id, location, file_path 
        FROM bbc_sounds 
        WHERE file_exists = false
    """)
    missing_files = cursor.fetchall()
    print(f"Found {len(missing_files)} entries with file_exists=false")
    print()
    
    # Build a map of location -> actual file path
    print("Scanning filesystem for WAV files...")
    location_to_path = {}
    
    for wav_file in SOUNDS_DIR.rglob("*.wav"):
        filename = wav_file.name
        location = extract_location_from_filename(filename)
        location_to_path[location] = str(wav_file)
    
    print(f"Found {len(location_to_path)} WAV files on disk")
    print()
    
    # Update database entries
    print("Updating database with correct file paths...")
    updated = 0
    not_found = 0
    
    for db_id, location, old_path in missing_files:
        if location in location_to_path:
            actual_path = location_to_path[location]
            
            # Update the database
            cursor.execute("""
                UPDATE bbc_sounds 
                SET file_path = %s, file_exists = true 
                WHERE id = %s
            """, (actual_path, db_id))
            
            updated += 1
            if updated % 100 == 0:
                conn.commit()
                print(f"Updated {updated} entries...")
        else:
            not_found += 1
    
    conn.commit()
    
    print()
    print("=" * 60)
    print("Update Complete!")
    print("=" * 60)
    print(f"Entries updated: {updated}")
    print(f"Entries still missing: {not_found}")
    print()
    
    # Show final statistics
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE file_exists = true) as exists,
            COUNT(*) FILTER (WHERE file_exists = false) as missing
        FROM bbc_sounds
    """)
    total, exists, missing = cursor.fetchone()
    
    print("Final Database Statistics:")
    print(f"  Total entries: {total}")
    print(f"  Files exist: {exists}")
    print(f"  Files missing: {missing}")
    print()
    
    cursor.close()
    conn.close()


if __name__ == "__main__":
    try:
        fix_file_paths()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
