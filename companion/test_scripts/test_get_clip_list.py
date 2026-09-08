#!/usr/bin/env python3
"""
Test script to try getting clip list from PTSL directly.
py-ptsl doesn't implement get_clip_list(), but PTSL has it!
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Add parent directory (companion/) to Python path
companion_dir = Path(__file__).parent.parent
sys.path.insert(0, str(companion_dir))

from ptsl import Engine
from ptsl import PTSL_pb2 as pt
from ptsl.ops import Operation
from typing import List


class GetClipList(Operation):
    """
    Custom operation to get clip list from PTSL.
    This operation exists in PTSL but py-ptsl hasn't implemented it.
    Command ID 125 from PTSL.proto (CId_GetClipList = 125)
    """
    
    @classmethod
    def command_id(cls):
        # GetClipList command ID from PTSL 2025.06
        return 125
    
    def __init__(self, **kwargs) -> None:
        self.clips = []
        self.raw_response_json = None
        super().__init__(**kwargs)


def test_get_clip_list():
    """Test if we can get clip list with positions."""
    
    print("[GET CLIP LIST TEST] Connecting to Pro Tools...")
    print("⚠️  Make sure Pro Tools is running with a session open!")
    print("⚠️  The session should have video clips on the timeline.\n")
    
    try:
        engine = Engine(company_name="MyCompany", application_name="TestApp")
    except Exception as e:
        print(f"\n❌ [CONNECTION FAILED] Could not connect to Pro Tools")
        print(f"Error: {e}")
        print("\nPossible reasons:")
        print("  1. Pro Tools is not running")
        print("  2. No session is open in Pro Tools")
        print("  3. PTSL is not enabled (Preferences > MIDI > Enable PTSL)")
        print("  4. Port 31416 is blocked or in use")
        return
    
    print("✅ Connected successfully!\n")
    
    try:
        # Get session info
        session_name = engine.session_name()
        print(f"[SESSION] {session_name}")
        
        # Try to get clip list
        print("[TRYING] GetClipList operation...")
        
        try:
            # Manually call the command and get JSON response
            import json
            response_json = engine.client.run_command(125, {})  # Command ID 125 = GetClipList
            
            print(f"\n[DEBUG] Raw response type: {type(response_json)}")
            if response_json:
                print(f"[DEBUG] Response keys: {response_json.keys()}")
            
            # Parse the clip_list from JSON
            if response_json and 'clip_list' in response_json:
                clips_data = response_json['clip_list']
                print(f"\n✅ [SUCCESS] Got {len(clips_data)} clips!")
                
                for i, clip_data in enumerate(clips_data):
                    print(f"\n{'='*60}")
                    print(f"[CLIP {i+1}]")
                    print(f"{'='*60}")
                    print(f"  Clip ID: {clip_data.get('clip_id', 'N/A')}")
                    print(f"  Name: {clip_data.get('clip_full_name', 'N/A')}")
                    print(f"  Type: {clip_data.get('clip_type', 'N/A')}")
                    print(f"  File ID: {clip_data.get('file_id', 'N/A')}")
                    
                    # TIMELINE POSITIONS!
                    if 'start_point' in clip_data:
                        start = clip_data['start_point']
                        print(f"  📍 Timeline Start: {start['position']} ({start['time_type']})")
                    
                    if 'end_point' in clip_data:
                        end = clip_data['end_point']
                        print(f"  📍 Timeline End: {end['position']} ({end['time_type']})")
                    
                    if 'sync_point' in clip_data:
                        sync = clip_data['sync_point']
                        print(f"  🎯 Sync Point: {sync['position']} ({sync['time_type']})")
                    
                    # SOURCE POSITIONS (if present)
                    if 'src_start_point' in clip_data:
                        src_start = clip_data['src_start_point']
                        print(f"  🎬 Source Start: {src_start['position']} ({src_start['time_type']})")
                    
                    if 'src_end_point' in clip_data:
                        src_end = clip_data['src_end_point']
                        print(f"  🎬 Source End: {src_end['position']} ({src_end['time_type']})")
            else:
                print("\n❌ No clips found in response!")
                print("The clip might not be in the Clips List (only on timeline)")
            
            # Done! All clips printed above
        
        except Exception as e:
            print(f"\n[ERROR] GetClipList failed: {e}")
            print(f"Error type: {type(e)}")
            import traceback
            traceback.print_exc()
    
    finally:
        pass


if __name__ == "__main__":
    try:
        test_get_clip_list()
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
