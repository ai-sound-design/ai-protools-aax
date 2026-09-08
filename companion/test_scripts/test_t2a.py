"""
Quick test script for T2A (Text-to-Audio) functionality

Tests the new T2A mode without video input.
"""

import sys
from pathlib import Path

# Add api module to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.client import generate_audio, check_api_health

def test_t2a_mode():
    """Test T2A (text-only audio generation)"""
    
    print("=" * 80)
    print("Testing T2A Mode (Text-to-Audio)")
    print("=" * 80)
    
    # Check API health
    print("\n1. Checking API health...")
    if not check_api_health(api_url="http://localhost:8000"):
        print("❌ API not available. Start the API first:")
        print("   cd standalone-API && python main.py")
        return False
    
    print("✅ API is online\n")
    
    # Test T2A generation
    print("2. Testing T2A generation (8 seconds, default)...")
    audio_path = generate_audio(
        api_url="http://localhost:8000",
        video_path=None,  # T2A mode: no video
        prompt="thunder and heavy rain",
        negative_prompt="voices, music",
        seed=42,
        duration=8.0,  # Required for T2A
        model_name="large_44k_v2",
        output_format="wav",
        verbose=True
    )
    
    if audio_path:
        print(f"\n✅ T2A test successful!")
        print(f"   Audio saved: {audio_path}")
        return True
    else:
        print("\n❌ T2A test failed")
        return False

if __name__ == "__main__":
    success = test_t2a_mode()
    sys.exit(0 if success else 1)
