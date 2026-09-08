"""
Preload MMAudio models into VRAM for standalone-API (MMAudio)

This script loads all MMAudio model components before the API receives any requests,
avoiding cold-start latency on the first generation request.

Usage:
    python preload_model.py [--model-size {small,medium,large}]
"""

import os
import sys
import time
import torch
import argparse
from pathlib import Path

# Add MMAudio to path
MMAUDIO_PATH = Path("/workspace/model-tests/repos/MMAudio")
sys.path.insert(0, str(MMAUDIO_PATH))

# Add shared module to path
SHARED_PATH = Path(__file__).parent.parent / "shared"
sys.path.insert(0, str(SHARED_PATH))

from config import FORCE_DEVICE, FORCE_DTYPE, ALLOW_TF32

# Import MMAudio components
from mmaudio.model.flow_matching import FlowMatching
from mmaudio.model.networks import MMAudio, get_my_mmaudio
from mmaudio.model.sequence_config import SequenceConfig
from mmaudio.model.utils.features_utils import FeaturesUtils

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
    dtype = torch.bfloat16 if device == "cuda" else torch.float32

def main():
    parser = argparse.ArgumentParser(description="Preload MMAudio model")
    parser.add_argument("--model-size", type=str, default="large",
                       choices=["small", "medium", "large"],
                       help="Model size to preload (default: large)")
    args = parser.parse_args()
    
    print("=" * 80)
    print("MMAudio Model Preloading for standalone-API")
    print("=" * 80)
    
    print(f"\n📋 Configuration:")
    print(f"   Model Size: {args.model_size}")
    print(f"   Device: {device}")
    print(f"   Dtype: {dtype}")
    print(f"   TF32: {ALLOW_TF32}")
    
    # Start loading
    print(f"\n🔄 Loading MMAudio model components...")
    start_time = time.time()
    
    try:
        # Load feature extractor
        print("   Loading feature extractor (SigLIP2, Syncformer)...")
        feature_start = time.time()
        feature_utils = FeaturesUtils(
            tod_vae_ckpt=str(MMAUDIO_PATH / 'ext_weights' / 'v1-16.pth'),
            synchformer_ckpt=str(MMAUDIO_PATH / 'ext_weights' / 'synchformer_state_dict.pth'),
            enable_conditions=True,
            mode=args.model_size,
            device=device
        )
        feature_time = time.time() - feature_start
        print(f"   ✓ Feature extractor loaded in {feature_time:.2f}s")
        
        # Load main MMAudio model
        print("   Loading MMAudio main model...")
        model_start = time.time()
        seq_cfg = SequenceConfig()
        net: MMAudio = get_my_mmaudio(args.model_size).to(device, dtype).eval()
        net.load_weights(torch.load(str(MMAUDIO_PATH / 'weights' / f'mmaudio_{args.model_size}_44k_v2.pth'),
                                    map_location=device, weights_only=True))
        model_time = time.time() - model_start
        print(f"   ✓ Main model loaded in {model_time:.2f}s")
        
        total_time = time.time() - start_time
        print(f"\n✓ All components loaded in {total_time:.2f}s")
        
        # GPU memory info
        if device == "cuda":
            allocated = torch.cuda.memory_allocated() / 1024**3
            reserved = torch.cuda.memory_reserved() / 1024**3
            print(f"\n💾 GPU Memory:")
            print(f"   Allocated: {allocated:.2f} GB")
            print(f"   Reserved: {reserved:.2f} GB")
        
        print(f"\n✅ MMAudio model successfully preloaded and ready!")
        print("=" * 80)
        return 0
        
    except Exception as e:
        print(f"\n❌ Error loading model: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
