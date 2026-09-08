"""
Test script for automatic clip detection workflow.

This script tests the complete automatic clip detection workflow:
1. Connect to Pro Tools via PTSL
2. Read session framerate
3. Get selected video clip info from Clips List
4. Calculate trim points from clip boundaries
5. Print results for verification

Usage:
    python test_auto_detect_workflow.py

Prerequisites:
    - Pro Tools running with PTSL enabled
    - Video clip selected in Pro Tools (should be in Clips List)
    - Clip can be cut/trimmed to test boundary detection
"""

import sys
from pathlib import Path

# Ensure ptsl is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_automatic_workflow():
    """Test the complete automatic clip detection workflow."""
    print("=" * 60)
    print("Testing Automatic Clip Detection Workflow")
    print("=" * 60)
    print()
    
    # Import PTSL
    try:
        from ptsl import open_engine
        print("✅ PTSL imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import PTSL: {e}")
        print("   Make sure py-ptsl is installed: pip install py-ptsl")
        return 1
    
    # Import clip detection functions
    try:
        from ptsl_integration.clip_info import (
            get_session_framerate,
            get_clip_info_for_selected_video,
            calculate_trim_points_from_clip
        )
        print("✅ Clip detection module imported")
    except ImportError as e:
        print(f"❌ Failed to import clip_info module: {e}")
        return 1
    
    print()
    print("Connecting to Pro Tools...")
    print()
    
    try:
        with open_engine(
            company_name="YourCompany",
            application_name="ProTools V2A Plugin Test"
        ) as engine:
            print("✅ Connected to Pro Tools!")
            print()
            
            # Step 1: Get session framerate
            print("--- Step 1: Session Framerate ---")
            try:
                fps = get_session_framerate(engine)
                print(f"✅ Session framerate: {fps} fps")
            except Exception as e:
                print(f"❌ Failed to get framerate: {e}")
                return 1
            
            print()
            
            # Step 2: Get selected clip info
            print("--- Step 2: Get Selected Video Clip ---")
            try:
                clip_info = get_clip_info_for_selected_video(engine)
                
                if not clip_info:
                    print("❌ No video clip found in Clips List")
                    print()
                    print("💡 To test this workflow:")
                    print("   1. Import a video clip into Pro Tools")
                    print("   2. (Optional) Cut the clip using Blade tool")
                    print("   3. Select the clip")
                    print("   4. Run this test script again")
                    return 1
                
                print(f"✅ Found clip: {clip_info.get('clip_name', 'Unknown')}")
                print(f"   File ID: {clip_info['file_id']}")
                print(f"   Frame range: {clip_info['start_frame']} - {clip_info['end_frame']}")
                
            except Exception as e:
                print(f"❌ Failed to get clip info: {e}")
                import traceback
                traceback.print_exc()
                return 1
            
            print()
            
            # Step 3: Calculate trim points
            print("--- Step 3: Calculate Trim Points ---")
            try:
                trim_info = calculate_trim_points_from_clip(clip_info, fps)
                
                print(f"✅ Trim points calculated:")
                print(f"   Start: {trim_info['start_seconds']:.3f}s (frame {clip_info['start_frame']})")
                print(f"   End: {trim_info['end_seconds']:.3f}s (frame {clip_info['end_frame']})")
                print(f"   Duration: {trim_info['duration_seconds']:.3f}s")
                
            except Exception as e:
                print(f"❌ Failed to calculate trim points: {e}")
                import traceback
                traceback.print_exc()
                return 1
            
            print()
            
            # Step 4: Show FFmpeg command preview
            print("--- Step 4: FFmpeg Command Preview ---")
            print(f"This would trim the video file using:")
            print(f"  ffmpeg -ss {trim_info['start_seconds']:.3f} -to {trim_info['end_seconds']:.3f} -i <input.mp4> -c copy <output.mp4>")
            
            print()
            print("=" * 60)
            print("✅ Automatic Clip Detection Test PASSED!")
            print("=" * 60)
            print()
            print("💡 Workflow Summary:")
            print(f"   1. Session framerate detected: {fps} fps")
            print(f"   2. Clip found: {clip_info.get('clip_name', 'Unknown')}")
            print(f"   3. Clip uses frames {clip_info['start_frame']}-{clip_info['end_frame']} from source")
            print(f"   4. This corresponds to {trim_info['start_seconds']:.3f}s-{trim_info['end_seconds']:.3f}s in source video")
            print(f"   5. FFmpeg will extract exactly {trim_info['duration_seconds']:.3f}s of video")
            print()
            print("🎯 Result: The system can automatically detect clip boundaries!")
            print("   No manual offset entry needed when clips are cut in Pro Tools.")
            
            return 0
            
    except Exception as e:
        print(f"❌ PTSL connection failed: {e}")
        print()
        print("Make sure:")
        print("  - Pro Tools is running")
        print("  - PTSL is enabled (Setup > Peripherals > Ethernet Controllers)")
        print("  - A session is open")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(test_automatic_workflow())
