"""
Preload HunyuanVideo-Foley model into VRAM for hunyuanvideo-foley-API

This script loads the HunyuanVideo-Foley model before the API receives any requests,
avoiding cold-start latency (10+ minutes for xxl model on HDD) on the first generation request.

Usage:
    python preload_model.py [--variant {xl,xxl}] [--offload]
"""

import os
import sys
import time
import torch
import argparse
from pathlib import Path

# Add HunyuanVideo-Foley to path
HYVF_PATH = Path("/workspace/model-tests/repos/HunyuanVideo-Foley")
sys.path.insert(0, str(HYVF_PATH))

# Add shared module to path
SHARED_PATH = Path(__file__).parent.parent / "shared"
sys.path.insert(0, str(SHARED_PATH))

from config import FORCE_DEVICE, FORCE_DTYPE, ALLOW_TF32, HYVF_WEIGHTS_PATH

# Import HunyuanVideo-Foley components
from hunyuanvideo_foley.utils.model_utils import load_model
from hunyuanvideo_foley.utils.config_utils import load_yaml

# Configure PyTorch
torch.backends.cuda.matmul.allow_tf32 = ALLOW_TF32
torch.backends.cudnn.allow_tf32 = ALLOW_TF32

# Device setup
if FORCE_DEVICE:
    device = FORCE_DEVICE
else:
    device = "cuda" if torch.cuda.is_available() else "cpu"

def main():
    parser = argparse.ArgumentParser(description="Preload HunyuanVideo-Foley model")
    parser.add_argument("--variant", type=str, default="xl",
                       choices=["xl", "xxl"],
                       help="Model variant to preload: xl (5.5GB, ~5min) or xxl (9.6GB, ~10min) [default: xl]")
    parser.add_argument("--offload", action="store_true",
                       help="Enable CPU offloading (slower inference, faster loading, less VRAM)")
    args = parser.parse_args()
    
    print("=" * 80)
    print("HunyuanVideo-Foley Model Preloading for hunyuanvideo-foley-API")
    print("=" * 80)
    
    # Configuration paths
    config_path = HYVF_PATH / "configs" / f"hunyuanvideo-foley-{args.variant}.yaml"
    
    # Model file selection
    if args.variant == "xl":
        model_file = "hunyuanvideo_foley_xl.pth"
        model_size = "5.5GB"
    else:  # xxl
        model_file = "hunyuanvideo_foley.pth"
        model_size = "9.6GB"
    
    print(f"\n📋 Configuration:")
    print(f"   Variant: {args.variant} ({model_size})")
    print(f"   Config: {config_path}")
    print(f"   Weights: {HYVF_WEIGHTS_PATH}/{model_file}")
    print(f"   Device: {device}")
    print(f"   Offload: {'enabled' if args.offload else 'disabled'}")
    print(f"   TF32: {ALLOW_TF32}")
    
    if args.variant == "xxl":
        print(f"\n⚠️  WARNING: xxl model is 9.6GB and may take 10+ minutes to load from HDD!")
        print(f"   Consider using --variant xl (5.5GB, ~5min) for faster loading.")
    
    # Start loading
    print(f"\n🔄 Loading HunyuanVideo-Foley {args.variant} model...")
    print(f"   This may take several minutes, please be patient...")
    start_time = time.time()
    
    try:
        # Load configuration
        cfg = load_yaml(str(config_path))
        
        # Load model (this is the slow part - reading 5.5-9.6GB from disk)
        model_dict, loaded_cfg = load_model(
            config_path=str(config_path),
            ckpt_path=str(HYVF_WEIGHTS_PATH),
            device=device,
            offload=args.offload
        )
        
        load_time = time.time() - start_time
        
        print(f"\n✓ Model loaded in {load_time:.2f}s ({load_time/60:.1f} minutes)")
        print(f"   Model components: {list(model_dict.keys())}")
        
        # GPU memory info
        if device == "cuda" and not args.offload:
            allocated = torch.cuda.memory_allocated() / 1024**3
            reserved = torch.cuda.memory_reserved() / 1024**3
            print(f"\n💾 GPU Memory:")
            print(f"   Allocated: {allocated:.2f} GB")
            print(f"   Reserved: {reserved:.2f} GB")
        
        print(f"\n✅ HunyuanVideo-Foley {args.variant} model successfully preloaded and ready!")
        print("=" * 80)
        return 0
        
    except Exception as e:
        print(f"\n❌ Error loading model: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
