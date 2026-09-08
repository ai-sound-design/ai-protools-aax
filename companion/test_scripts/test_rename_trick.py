"""
Test: Use rename_selected_clip() to identify which clip is selected.

Strategy:
1. Rename selected clip to temporary unique name
2. Call GetClipList to find clip with that name
3. Rename back to original name
4. Now we know which clip was selected!
"""

import sys
import os
import uuid
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Add parent directory (companion/) to Python path
companion_dir = Path(__file__).parent.parent
sys.path.insert(0, str(companion_dir))

from ptsl import open_engine
from ptsl.PTSL_pb2 import ClipLocation

print("=" * 60)
print("Testing: Rename Trick to Identify Selected Clip")
print("=" * 60)
print()
print("⚠️  Please SELECT a clip in the Clips List!")
print("⚠️  (e.g., 'test_dogBarking-02')")
print()

with open_engine(company_name="YourCompany", application_name="PTSLTest") as engine:
    print("✅ Connected to Pro Tools")
    print()
    
    try:
        # Step 1: Get list of clips BEFORE rename
        print("--- Step 1: Get clips before rename ---")
        response_before = engine.client.run_command(125, {})  # GetClipList
        
        if not response_before or 'clip_list' not in response_before:
            print("❌ No clips found!")
            sys.exit(1)
        
        clips_before = response_before['clip_list']
        print(f"Found {len(clips_before)} clips:")
        for clip in clips_before:
            print(f"  - {clip.get('clip_full_name')}")
        print()
        
        # Step 2: Generate temporary unique name
        temp_name = f"__TEMP_SELECTED_{uuid.uuid4().hex[:8]}__"
        print(f"--- Step 2: Rename selected clip to '{temp_name}' ---")
        
        # Use ClipsList location (since the clip is highlighted there)
        if hasattr(ClipLocation, 'CLocation_ClipsList'):
            clip_loc = ClipLocation.CLocation_ClipsList
        else:
            clip_loc = ClipLocation.CL_ClipsList
        
        # Rename the selected clip (rename_file=False to not touch the file!)
        engine.rename_selected_clip(
            new_name=temp_name,
            rename_file=False,
            clip_location=clip_loc
        )
        
        print("✅ Rename successful!")
        print()
        
        # Step 3: Get list of clips AFTER rename
        print("--- Step 3: Find the renamed clip ---")
        response_after = engine.client.run_command(125, {})  # GetClipList
        
        if not response_after or 'clip_list' not in response_after:
            print("❌ No clips found after rename!")
            sys.exit(1)
        
        clips_after = response_after['clip_list']
        
        # Find the clip with the temporary name
        selected_clip = None
        original_name = None
        
        for clip in clips_after:
            if clip.get('clip_full_name') == temp_name:
                selected_clip = clip
                
                # Find the original name by comparing with clips_before
                for old_clip in clips_before:
                    if old_clip.get('clip_id') == clip.get('clip_id'):
                        original_name = old_clip.get('clip_full_name')
                        break
                
                break
        
        if not selected_clip:
            print("❌ Could not find renamed clip!")
            sys.exit(1)
        
        print(f"✅ Found selected clip!")
        print(f"   Original name: {original_name}")
        print(f"   clip_id: {selected_clip.get('clip_id')}")
        print(f"   file_id: {selected_clip.get('file_id')}")
        
        start_frames = selected_clip.get('start_point', {}).get('value', 0)
        end_frames = selected_clip.get('end_point', {}).get('value', 0)
        print(f"   Frames: {start_frames} - {end_frames}")
        print()
        
        # Step 4: Rename back to original name
        print(f"--- Step 4: Rename back to '{original_name}' ---")
        
        engine.rename_selected_clip(
            new_name=original_name,
            rename_file=False,
            clip_location=clip_loc
        )
        
        print("✅ Restored original name!")
        print()
        
        # Step 5: Verify
        print("--- Step 5: Verify restoration ---")
        response_verify = engine.client.run_command(125, {})  # GetClipList
        clips_verify = response_verify['clip_list']
        
        found_original = False
        for clip in clips_verify:
            if clip.get('clip_id') == selected_clip.get('clip_id'):
                print(f"✅ Clip name is now: {clip.get('clip_full_name')}")
                found_original = True
                break
        
        if not found_original:
            print("⚠️  Could not verify restoration")
        
        print()
        
        # Success!
        print("=" * 60)
        print("🎉 SUCCESS!")
        print("=" * 60)
        print()
        print(f"The selected clip is: {original_name}")
        print(f"  clip_id: {selected_clip.get('clip_id')}")
        print(f"  file_id: {selected_clip.get('file_id')}")
        print(f"  Frames: {start_frames} - {end_frames}")
        print()
        print("💡 This method works perfectly!")
        print("   We can now identify the exact selected clip!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
