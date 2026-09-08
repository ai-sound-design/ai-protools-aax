"""
Test: PTSL Import to Pro Tools timeline with pre-generated audio 

Using py-ptsl library. 

Prerequisites: 
- Pro Tools running with PTSL enabled
- A session open in Pro Tools
- venv with installed dependencies:
    -- py-ptsl (pip install -e ../../external/py-ptsl)
    -- requirements from companion/requirements.txt
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ptsl_integration import import_audio_to_pro_tools

def test_full_workflow():
    """Test complete workflow: Generate audio and import to Pro Tools"""
    
    print("="*60)
    print("PTSL Integration Test (py-ptsl)")
    print("="*60)
    
    # Step 1: Find test audio file
    print("\n1. Looking for test audio file...")
    
    # Try multiple possible locations for test audio
    test_locations = [
        Path("C:/Users/USERNA~1/AppData/Local/Temp/pt_v2a_outputs"),
        Path(__file__).parent.parent / "test-data",
        Path(__file__).parent / "test-data"
    ]
    
    test_audio_file = None
    for location in test_locations:
        if location.exists():
            # Try FLAC first, then WAV
            for pattern in ["*.flac", "*.wav"]:
                files = list(location.glob(pattern))
                if files:
                    test_audio_file = files[0]
                    break
        if test_audio_file:
            break
    
    if not test_audio_file:
        print("⚠️  No test audio file found")
        print("   Searched locations:")
        for loc in test_locations:
            print(f"     - {loc}")
        print("\n   Run the plugin or standalone API client to generate audio first")
        return False
    
    print(f"✅ Found: {test_audio_file}")
    
    # Step 2: Import to Pro Tools using py-ptsl
    print("\n2. Importing to Pro Tools via py-ptsl...")
    print(f"   File: {test_audio_file}")
    print(f"   Location: SessionStart (sample 0)")
    
    success = import_audio_to_pro_tools(
        audio_path=str(test_audio_file),
        location="SessionStart"
    )
    
    if not success:
        print("❌ Import failed")
        print("\nMake sure:")
        print("  - Pro Tools is running")
        print("  - PTSL is enabled (Setup > Preferences > MIDI > Enable PTSL)")
        print("  - A session is open in Pro Tools")
        print("  - py-ptsl is installed (pip install -e ../../external/py-ptsl)")
        return False
    
    print("\n" + "="*60)
    print("✅ All tests passed!")
    print("="*60)
    print("\npy-ptsl integration working correctly!")
    return True


if __name__ == "__main__":
    success = test_full_workflow()
    sys.exit(0 if success else 1)
