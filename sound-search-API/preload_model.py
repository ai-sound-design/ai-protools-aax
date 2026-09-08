"""
Preload X-CLIP model into VRAM for sound-search-API

This script loads the X-CLIP model before the API receives any requests,
avoiding cold-start latency on the first search query.

Usage:
    python preload_model.py
"""

import os
import sys
import time
import torch
from pathlib import Path

# Add shared module to path
SHARED_PATH = Path(__file__).parent.parent / "shared"
sys.path.insert(0, str(SHARED_PATH))

from config import FORCE_DEVICE, FORCE_DTYPE, ALLOW_TF32

# Import X-CLIP encoder
from utils.xclip_encoder import XCLIPEncoder

# Configure PyTorch
torch.backends.cuda.matmul.allow_tf32 = ALLOW_TF32
torch.backends.cudnn.allow_tf32 = ALLOW_TF32

# Device setup
if FORCE_DEVICE:
    device = FORCE_DEVICE
else:
    device = "cuda" if torch.cuda.is_available() else "cpu"

# Data type
if FORCE_DTYPE:
    dtype = getattr(torch, FORCE_DTYPE)
else:
    dtype = torch.float16 if device == "cuda" else torch.float32

def main():
    print("=" * 80)
    print("X-CLIP Model Preloading for sound-search-API")
    print("=" * 80)
    
    # Model configuration
    model_name = "microsoft/xclip-base-patch32"
    num_frames = 16
    
    print(f"\n📋 Configuration:")
    print(f"   Model: {model_name}")
    print(f"   Device: {device}")
    print(f"   Dtype: {dtype}")
    print(f"   Num Frames: {num_frames}")
    print(f"   TF32: {ALLOW_TF32}")
    
    # Start loading
    print(f"\n🔄 Loading X-CLIP model...")
    start_time = time.time()
    
    try:
        # Initialize encoder (will load model into VRAM)
        encoder = XCLIPEncoder(
            model_name=model_name,
            device=device,
            dtype=dtype,
            num_frames=num_frames,
            use_compile=True  # Use torch.compile for optimization
        )
        
        load_time = time.time() - start_time
        
        # Test encoding to ensure model is fully loaded
        print(f"✓ Model loaded in {load_time:.2f}s")
        print(f"\n🧪 Testing model with sample text encoding...")
        
        test_start = time.time()
        test_text = "footsteps on gravel"
        _ = encoder.encode_text([test_text])
        test_time = time.time() - test_start
        
        print(f"✓ Test encoding completed in {test_time*1000:.1f}ms")
        
        # GPU memory info
        if device == "cuda":
            allocated = torch.cuda.memory_allocated() / 1024**3
            reserved = torch.cuda.memory_reserved() / 1024**3
            print(f"\n💾 GPU Memory:")
            print(f"   Allocated: {allocated:.2f} GB")
            print(f"   Reserved: {reserved:.2f} GB")
        
        print(f"\n✅ X-CLIP model successfully preloaded and ready!")
        print("=" * 80)
        return 0
        
    except Exception as e:
        print(f"\n❌ Error loading model: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
