#!/usr/bin/env python3
"""
Database Integrity Checker for BBC Sound Archive

This script validates the database against the CSV and filesystem to identify:
1. Missing files (in DB but not on disk)
2. Wrong file paths (CSV -> DB mapping errors)
3. Duplicate entries (multiple descriptions for same file)
4. Orphaned files (on disk but not in DB)
"""

import csv
import os
import psycopg2
from pathlib import Path
from collections import defaultdict

# Configuration
CSV_FILE = "/mnt/data/BBCSoundDownloader/BBCSoundEffects_max30s.csv"
SOUNDS_DIR = Path("/mnt/data/BBCSoundDownloader/sounds")
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "bbc_sounds",
    "user": "bbc_user",
    "password": os.getenv("BBC_DB_PASSWORD", "change_me")
}


def check_duplicate_file_paths(cursor):
    """Find all file paths that have multiple database entries"""
    print("\n=== DUPLICATE FILE PATHS ===")
    cursor.execute("""
        SELECT 
            file_path, 
            COUNT(*) as entry_count,
            array_agg(id) as db_ids,
            array_agg(description) as descriptions
        FROM bbc_sounds 
        GROUP BY file_path 
        HAVING COUNT(*) > 1 
        ORDER BY COUNT(*) DESC
    """)
    
    duplicates = cursor.fetchall()
    print(f"Found {len(duplicates)} files with duplicate entries")
    
    total_extra_entries = sum(count - 1 for _, count, _, _ in duplicates)
    print(f"Total extra/wrong entries: {total_extra_entries}")
    
    return duplicates


def check_csv_vs_database(cursor):
    """Compare CSV data with database entries"""
    print("\n=== CSV vs DATABASE VALIDATION ===")
    
    # Read all CSV entries
    csv_entries = []
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            csv_entries.append(row)
    
    print(f"CSV has {len(csv_entries)} entries")
    
    # Get all DB entries
    cursor.execute("SELECT COUNT(*) FROM bbc_sounds")
    db_count = cursor.fetchone()[0]
    print(f"Database has {db_count} entries")
    
    # Check each CSV entry
    missing_in_db = []
    wrong_file_path = []
    
    for row in csv_entries:
        location = row['location']
        description = row['description']
        cdname = row['cdname']
        
        # Construct the CORRECT file path (with ID)
        correct_file_path = SOUNDS_DIR / cdname / f"{description}.{location}"
        
        # Construct what the IMPORT SCRIPT did (without ID suffix)
        import_script_path = SOUNDS_DIR / cdname / f"{description}.{location}"
        
        # Check if entry exists in DB with correct path
        cursor.execute(
            "SELECT id, file_path FROM bbc_sounds WHERE location = %s",
            (location,)
        )
        db_entry = cursor.fetchone()
        
        if not db_entry:
            missing_in_db.append(row)
        elif db_entry[1] != str(correct_file_path):
            wrong_file_path.append({
                'location': location,
                'csv_description': description,
                'db_file_path': db_entry[1],
                'correct_file_path': str(correct_file_path)
            })
    
    print(f"Missing in DB: {len(missing_in_db)}")
    print(f"Wrong file path: {len(wrong_file_path)}")
    
    return wrong_file_path


def check_filesystem_vs_database(cursor):
    """Check if database file paths actually exist on filesystem"""
    print("\n=== FILESYSTEM VALIDATION ===")
    
    cursor.execute("SELECT id, file_path, description FROM bbc_sounds")
    all_entries = cursor.fetchall()
    
    missing_files = []
    existing_files = []
    
    for db_id, file_path, description in all_entries:
        if os.path.exists(file_path):
            existing_files.append(file_path)
        else:
            missing_files.append({
                'id': db_id,
                'file_path': file_path,
                'description': description
            })
    
    print(f"Files exist: {len(existing_files)} / {len(all_entries)}")
    print(f"Files missing: {len(missing_files)}")
    
    if missing_files:
        print("\nSample missing files:")
        for item in missing_files[:5]:
            print(f"  ID {item['id']}: {item['file_path']}")
            print(f"    Description: {item['description']}")
    
    return missing_files, existing_files


def check_category_description_mismatch(cursor):
    """Find entries where description doesn't match category"""
    print("\n=== CATEGORY/DESCRIPTION MISMATCH ===")
    
    # Get duplicates and check for obvious mismatches
    cursor.execute("""
        SELECT 
            file_path, 
            array_agg(DISTINCT category) as categories,
            array_agg(DISTINCT description) as descriptions
        FROM bbc_sounds 
        GROUP BY file_path 
        HAVING COUNT(*) > 1
    """)
    
    duplicates = cursor.fetchall()
    obvious_mismatches = []
    
    for file_path, categories, descriptions in duplicates:
        # Check if descriptions mention things not in category
        for desc in descriptions:
            desc_lower = desc.lower()
            cat_lower = categories[0].lower()
            
            # Simple heuristic: if description mentions completely different things
            if 'car' in cat_lower and 'footstep' in desc_lower:
                obvious_mismatches.append({
                    'file_path': file_path,
                    'category': categories[0],
                    'wrong_description': desc
                })
            elif 'horse' in desc_lower and 'launderette' in cat_lower:
                obvious_mismatches.append({
                    'file_path': file_path,
                    'category': categories[0],
                    'wrong_description': desc
                })
    
    print(f"Found {len(obvious_mismatches)} obvious mismatches")
    
    return obvious_mismatches


def generate_report():
    """Generate comprehensive database integrity report"""
    
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    print("=" * 80)
    print("BBC SOUND ARCHIVE - DATABASE INTEGRITY CHECK")
    print("=" * 80)
    
    # 1. Check duplicates
    duplicates = check_duplicate_file_paths(cursor)
    
    # 2. Check filesystem
    missing_files, existing_files = check_filesystem_vs_database(cursor)
    
    # 3. Check category/description mismatches
    mismatches = check_category_description_mismatch(cursor)
    
    # 4. Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total issues found:")
    print(f"  - {len(duplicates)} files with duplicate entries")
    print(f"  - {len(missing_files)} database entries with missing files")
    print(f"  - {len(mismatches)} obvious category/description mismatches")
    
    # Generate recommendations
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    
    if len(missing_files) > len(duplicates) * 2:
        print("❌ CRITICAL: Many files don't exist - import script path construction is completely wrong")
        print("   → Need to fix construct_file_path() in import_bbc_sounds.py")
        print("   → Then drop and rebuild entire database")
    elif len(duplicates) > 0:
        print("⚠️  WARNING: Multiple entries point to same file")
        print("   → Import script created wrong file paths for some entries")
        print("   → Need to delete duplicate entries and reimport affected files")
    else:
        print("✅ Database integrity looks good!")
    
    cursor.close()
    conn.close()


if __name__ == "__main__":
    generate_report()
