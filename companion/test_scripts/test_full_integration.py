"""
Test Full Integration of Automatic Clip Detection with standalone_api_client.py

This script simulates a full workflow:
1. User selects a video clip in Pro Tools (manual step)
2. Script auto-detects clip boundaries
3. Script trims video to match clip
4. Script generates audio for the trimmed video

Prerequisites:
- Pro Tools is running
- A video clip is imported and selected in Pro Tools
- The video file exists on disk
"""

import sys
import os
from pathlib import Path

# Add parent directory (companion/) to Python path
companion_dir = Path(__file__).parent.parent
sys.path.insert(0, str(companion_dir))

def test_full_integration():
    """Test the complete workflow with automatic clip detection"""
    
    print("=" * 60)
    print("Testing Full Integration: Pro Tools → Video → Audio")
    print("=" * 60)
    print()
    
    # Test parameters
    video_file = r"c:\Users\Username\model-tests\data\customMicroFoleyTestSet\noSound\test_dogBarking.mp4"
    output_dir = r"c:\Users\Username\protools-aax\companion\test_outputs"
    output_file = os.path.join(output_dir, "test_integration_output.flac")
    
    # Check if video file exists
    if not os.path.exists(video_file):
        print(f"❌ Video file not found: {video_file}")
        print(f"   Please update the video_file path in this script")
        return 1
    
    # Create output directory if needed
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"📹 Video file: {Path(video_file).name}")
    print(f"📁 Output file: {output_file}")
    print()
    
    print("💡 Prerequisites:")
    print("   1. Pro Tools is running")
    print("   2. Video clip is imported into Pro Tools")
    print("   3. Video clip is selected (highlighted in Clips List)")
    print()
    
    input("Press Enter when ready to test (or Ctrl+C to cancel)...")
    print()
    
    # Import the main function
    try:
        from standalone_api_client import main
        print("✅ Imported standalone_api_client")
    except Exception as e:
        print(f"❌ Failed to import standalone_api_client: {e}")
        return 1
    
    # Prepare command-line arguments for the test
    # Simulating: python standalone_api_client.py --video test_dogBarking.mp4 --auto-detect-clip --import-to-protools --output test_output.flac
    sys.argv = [
        'standalone_api_client.py',
        '--video', video_file,
        '--auto-detect-clip',
        '--import-to-protools',  # NEW: Import generated audio back to Pro Tools
        '--output', output_file,
        '--prompt', 'Dog barking outdoors',
        '--verbose'
    ]
    
    print("🚀 Running standalone_api_client with auto-detect-clip...")
    print(f"   Command: {' '.join(sys.argv)}")
    print()
    print("-" * 60)
    
    try:
        # Run the main function
        result = main()
        
        print("-" * 60)
        print()
        
        if result == 0:
            print("✅ Integration test PASSED!")
            print()
            print("🎯 Workflow Summary:")
            print("   1. ✅ Connected to Pro Tools")
            print("   2. ✅ Detected clip boundaries automatically")
            print("   3. ✅ Trimmed video to match clip")
            print("   4. ✅ Generated audio for trimmed video")
            print("   5. ✅ Imported audio back to Pro Tools timeline")
            print()
            print(f"📁 Output file: {output_file}")
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file) / 1024  # KB
                print(f"   File size: {file_size:.1f} KB")
        else:
            print(f"❌ Integration test FAILED (exit code: {result})")
            
        return result
        
    except KeyboardInterrupt:
        print("\n⚠️  Test cancelled by user")
        return 1
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(test_full_integration())
