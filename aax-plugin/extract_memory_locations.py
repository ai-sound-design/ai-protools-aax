#!/usr/bin/env python3
"""
Extract Memory Locations from Pro Tools Session

This script reads all memory locations from the currently open Pro Tools session
and outputs them in a Python-friendly format for hardcoding into auto_spotting_wizard.py.

Usage:
    1. Open your test session in Pro Tools
    2. Create memory locations at desired positions (markers for audio events)
    3. Run this script: python extract_memory_locations.py
    4. Copy the output and paste into auto_spotting_wizard.py MEMORY_LOCATIONS list
    5. Delete the memory locations from the session (they will be recreated by the wizard)

Requirements:
    - Pro Tools running with session open
    - py-ptsl installed (pip install py-ptsl)
    - PTSL server running in Pro Tools
"""

from ptsl import open_engine
import ptsl.PTSL_pb2 as pt

def main():
    print("=" * 80)
    print("Memory Location Extractor for Auto Spotting Wizard")
    print("=" * 80)
    print()
    
    try:
        # Connect to Pro Tools via PTSL
        print("Connecting to Pro Tools...")
        with open_engine(
            company_name="Master Thesis",
            application_name="Memory Location Extractor"
        ) as engine:
            print(f"✓ Connected to Pro Tools")
            print(f"✓ Session: {engine.session_name()}")
            print()
            
            # Get all memory locations
            print("Reading memory locations...")
            locations = engine.get_memory_locations()
            
            if not locations:
                print("⚠ No memory locations found in session!")
                print("Please create some memory locations first, then run this script again.")
                return
            
            print(f"✓ Found {len(locations)} memory location(s)")
            print()
            
            # Output Python list format
            print("=" * 80)
            print("Copy the following into auto_spotting_wizard.py:")
            print("=" * 80)
            print()
            print("MEMORY_LOCATIONS = [")
            
            for loc in locations:
                # Extract relevant fields
                name = loc.name
                start_time = loc.start_time
                end_time = loc.end_time
                color_index = loc.color_index
                # Extract location enum - convert to string name for Python code
                location = pt.MarkerLocation.Name(loc.location)
                # Track name contains ruler name for MarkerLocation_NamedRuler (e.g. "DIA", "FX", "MX")
                track_name = loc.track_name if loc.track_name else ""
                
                # Format as Python tuple (name, start, end, color, location, track)
                print(f'    ("{name}", "{start_time}", "{end_time}", {color_index}, "{location}", "{track_name}"),')
            
            print("]")
            print()
            
            # Summary
            print("=" * 80)
            print("Summary:")
            print("=" * 80)
            for i, loc in enumerate(locations, 1):
                print(f"{i}. {loc.name} @ {loc.start_time} (color: {loc.color_index})")
            
            print()
            print("✓ Extraction complete!")
            print()
            print("Next steps:")
            print("1. Copy the MEMORY_LOCATIONS list above")
            print("2. Paste it into auto_spotting_wizard.py (replace existing list)")
            print("3. Delete the memory locations from your Pro Tools session")
            print("4. The Auto Spotting wizard will recreate them during the fake progress")
            
    except Exception as e:
        print(f"✗ Error: {e}")
        print()
        print("Troubleshooting:")
        print("- Make sure Pro Tools is running")
        print("- Make sure a session is open")
        print("- Make sure PTSL server is active in Pro Tools")
        print("- Check that py-ptsl is installed: pip install py-ptsl")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
