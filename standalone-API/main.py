"""
MMAudio Standalone API

"""

import os
import sys
import logging
import tracemalloc
from pathlib import Path
from typing import Optional
import hashlib
import pickle
import tempfile
import time
from datetime import datetime
import asyncio
import threading
import psutil
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, Optional

# Add shared module to path
SHARED_PATH = Path(__file__).parent.parent / "shared"
sys.path.insert(0, str(SHARED_PATH))

# Import shared configuration
from config import (
    API_HOST, API_PORT, LOG_LEVEL,
    VIDEO_CACHE_MAX_GB, VIDEO_CACHE_TTL_MIN, VIDEO_FRAME_CHECK,
    FORCE_DEVICE, FORCE_DTYPE,
    MMAUDIO_PATH, HYVF_PATH, HYVF_WEIGHTS_PATH,
    ALLOW_TF32, ENABLE_TRACEMALLOC, LOG_BUFFER_SIZE
)

import torch
import numpy as np
import av
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# GPU monitoring (optional dependency)
try:
    import pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False
    # pynvml not installed - GPU monitoring will be limited to torch.cuda

# Add MMAudio path to sys.path for imports
sys.path.insert(0, str(MMAUDIO_PATH))

try:
    from mmaudio.eval_utils import ModelConfig, all_model_cfg, generate, load_video, setup_eval_logging
    from mmaudio.model.flow_matching import FlowMatching  
    from mmaudio.model.networks import MMAudio, get_my_mmaudio
    from mmaudio.model.utils.features_utils import FeaturesUtils
    import torchaudio
    import torchaudio.transforms as T
except ImportError as e:
    logging.error(f"Failed to import MMAudio: {e}")
    logging.error("Please check MMAUDIO_PATH in the script")
    sys.exit(1)

# Configure logging with custom handler to capture logs (use logging from mmaudio.eval_utils)
setup_eval_logging()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ring buffer for storing recent log messages
from collections import deque
log_buffer = deque(maxlen=LOG_BUFFER_SIZE)

class BufferHandler(logging.Handler):
    """Custom log handler that stores logs in memory buffer"""
    def emit(self, record):
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S'),
                "level": record.levelname,
                "message": self.format(record),
                "module": record.module
            }
            log_buffer.append(log_entry)
        except Exception:
            self.handleError(record)

# Add buffer handler to root logger
buffer_handler = BufferHandler()
buffer_handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
logging.getLogger().addHandler(buffer_handler)

# Global configuration
torch.backends.cuda.matmul.allow_tf32 = ALLOW_TF32
torch.backends.cudnn.allow_tf32 = ALLOW_TF32

# Device selection (can be forced via FORCE_DEVICE env var)
if FORCE_DEVICE and FORCE_DEVICE != "auto":
    device = FORCE_DEVICE
    logger.info(f"🎯 Using forced device: {device}")
else:
    device = 'cpu'
    if torch.cuda.is_available():
        device = 'cuda'
        logger.info(f"🎯 Using CUDA device (GPU available)")
    elif torch.backends.mps.is_available():
        device = 'mps'
        logger.info(f"🎯 Using MPS device (Apple Silicon)")
    else:
        device = 'cpu'
        logger.warning('⚠️  CUDA/MPS not available, running on CPU')

# Dtype selection (can be forced via FORCE_DTYPE env var)
if FORCE_DTYPE and FORCE_DTYPE != "auto":
    dtype_map = {"float32": torch.float32, "bfloat16": torch.bfloat16, "float16": torch.float16}
    dtype = dtype_map.get(FORCE_DTYPE, torch.bfloat16)
    logger.info(f"🔧 Using forced precision: {dtype}")
else:
    dtype = torch.bfloat16
    logger.info(f"🔧 Default precision: {dtype}")

# ========== CACHE SYSTEM ==========
#
# ┌────────────────────────────────────────────────────────────────────────────┐
# │                           CACHE ARCHITECTURE                               │
# ├────────────────────────────────────────────────────────────────────────────┤
# │ TIER 1: MODEL_CACHE (VRAM/GPU Memory)                                      │
# │ ├─ Purpose: Cache loaded PyTorch models to avoid expensive model loading   │
# │ ├─ Storage: GPU VRAM                                                       │
# │ ├─ Lifetime: Until server restart                                          │
# │ ├─ Key: model_name (e.g., "large_44k_v2")                                  │              
# │ └─ Value: (MMAudio network, FeaturesUtils, ModelConfig)                    │
# │                                                                            │
# │ TIER 2: SMART_VIDEO_CACHE (System RAM)                                     │
# │ ├─ Purpose: Cache preprocessed video tensors with intelligent eviction     │
# │ ├─ Storage: System RAM (configurable, default 32GB limit)                  │
# │ ├─ Lifetime: LRU + TTL hybrid (90 minutes default)                         │
# │ ├─ Key: MD5(video_path + duration + file_mtime)                            │
# │ └─ Value: Preprocessed video_info (clip_frames, sync_frames, etc.)         │
# │                                                                            │
# │ TIER 3: CACHE_DIR (Disk Storage)                                           │
# │ ├─ Purpose: Temporary storage for generated audio files                    │
# │ ├─ Storage: Local filesystem                                               │
# │ ├─ Lifetime: Auto-cleanup (5 minutes immediate, 2 hours fallback)          │
# │ ├─ Key: Timestamp-based filenames                                          │
# │ └─ Value: Generated FLAC audio files                                       │
# └────────────────────────────────────────────────────────────────────────────┘
#
# SMART EVICTION STRATEGIES:
# 1. LRU (Least Recently Used): Removes oldest accessed videos when size limit hit
# 2. TTL (Time To Live): Background thread cleans expired videos every 15 minutes
# 3. Size-Based: Intelligent memory estimation and size-aware eviction
# 4. Thread-Safe: Concurrent access from multiple FastAPI workers
#
#
# CONFIGURATION:
# - VIDEO_CACHE_MAX_GB: Maximum RAM for video cache (default: 32GB)
# - VIDEO_CACHE_TTL_MIN: TTL for cached videos (default: 90 minutes)
# - Set via environment variables for production deployment
#
# MONITORING:
# - GET /cache/stats: Detailed cache statistics and memory usage
# - POST /cache/clear: Clear video cache (preserve models)
# - POST /cache/clear-all: Full cache reset including models

@dataclass
class CacheEntry:
    """Cache entry with metadata for LRU + TTL + Size tracking"""
    data: Any                   # The cached video_info object
    created_at: float           # Unix timestamp when cached
    last_accessed: float        # Unix timestamp of last access (LRU)
    estimated_size_mb: float    # Estimated memory usage in MB
    access_count: int = 0       # Number of times accessed (statistics)

class SmartVideoCache:
    """
    Hybrid LRU + TTL + Size-Limit Video Cache
    
    Features:
    - LRU Eviction: Removes least recently used videos when size limit reached
    - TTL Expiry: Automatic cleanup of old videos (configurable)
    - Size Limit: Maximum RAM usage with smart eviction
    - Statistics: Hit rate, memory usage, eviction metrics
    - Thread-safe: Can be accessed from multiple FastAPI workers
    """
    
    def __init__(self, max_size_gb: float = 32, ttl_minutes: int = 90):
        self.max_size_bytes = max_size_gb * 1024 * 1024 * 1024  # Convert to bytes
        self.ttl_seconds = ttl_minutes * 60
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions_lru': 0,
            'evictions_ttl': 0,
            'current_size_mb': 0,
            'total_entries': 0
        }
        self._lock = threading.RLock()  # Thread-safe access
        self._stop_cleanup = threading.Event()
        
        # Start background TTL cleanup thread
        self._cleanup_thread = threading.Thread(target=self._background_ttl_cleanup, daemon=True)
        self._cleanup_thread.start()
        logger.info(f"🕒 TTL cleanup thread started (interval: {max(ttl_minutes // 6, 5)} minutes)")
    
    def _estimate_tensor_size_mb(self, video_info) -> float:
        """
        Estimate memory usage of video_info object in MB
        
        IMPORTANT: Must count ALL tensors recursively, not just clip_frames/sync_frames!
        video_info contains many nested tensors that were previously uncounted.
        """
        try:
            size_bytes = 0
            
            # Recursively find all tensors in video_info object
            def count_tensors(obj, visited=None):
                if visited is None:
                    visited = set()
                
                # Avoid circular references
                obj_id = id(obj)
                if obj_id in visited:
                    return 0
                visited.add(obj_id)
                
                total = 0
                
                # Count torch.Tensor objects
                if isinstance(obj, torch.Tensor):
                    # element_size() returns bytes per element
                    # numel() returns total number of elements
                    total += obj.element_size() * obj.numel()
                
                # Recursively check attributes (for dataclass/object attributes)
                elif hasattr(obj, '__dict__'):
                    for attr_value in obj.__dict__.values():
                        total += count_tensors(attr_value, visited)
                
                # Recursively check dict values
                elif isinstance(obj, dict):
                    for value in obj.values():
                        total += count_tensors(value, visited)
                
                # Recursively check list/tuple items
                elif isinstance(obj, (list, tuple)):
                    for item in obj:
                        total += count_tensors(item, visited)
                
                return total
            
            size_bytes = count_tensors(video_info)
            
            # Add overhead for Python objects and CUDA alignment (~20%)
            size_bytes = int(size_bytes * 1.2)
            
            size_mb = size_bytes / (1024 * 1024)
            
            # Sanity check: if estimation seems too low, use conservative fallback
            if size_mb < 50:  # Videos should be at least 50 MB
                logger.warning(f"Suspiciously low size estimate: {size_mb:.1f}MB, using fallback 500MB")
                return 500.0
            
            return size_mb
            
        except Exception as e:
            logger.error(f"Size estimation failed: {e}, using fallback")
            # Fallback: conservative estimate for safety
            return 500.0
    
    def _cleanup_expired(self):
        """Remove expired entries based on TTL"""
        current_time = time.time()
        expired_keys = []
        
        for key, entry in self.cache.items():
            if current_time - entry.created_at > self.ttl_seconds:
                expired_keys.append(key)
        
        for key in expired_keys:
            entry = self.cache.pop(key)
            age_minutes = (current_time - entry.created_at) / 60
            self.stats['evictions_ttl'] += 1
            self.stats['current_size_mb'] -= entry.estimated_size_mb
            self.stats['total_entries'] -= 1
            
            # Log before deletion
            logger.info(f"🕒 TTL EVICTED: {key[:8]}... (age: {age_minutes:.1f}min)")
            
            # Explicitly delete tensors to free memory
            del entry.data
            del entry
    
    def _background_ttl_cleanup(self):
        """Background thread for periodic TTL cleanup (runs even when API is idle)"""
        # Run cleanup every 15 minutes or 1/6 of TTL (whichever is larger)
        cleanup_interval = max(self.ttl_seconds / 6, 900)  # Minimum 5 minutes
        
        while not self._stop_cleanup.is_set():
            self._stop_cleanup.wait(cleanup_interval)
            
            if self._stop_cleanup.is_set():
                break
            
            # Perform TTL cleanup with lock
            with self._lock:
                if self.cache:
                    before_count = len(self.cache)
                    before_size = self.stats['current_size_mb']
                    self._cleanup_expired()
                    after_count = len(self.cache)
                    
                    if before_count != after_count:
                        freed_mb = before_size - self.stats['current_size_mb']
                        logger.info(f"🧹 Background TTL cleanup: {before_count - after_count} videos evicted, {freed_mb:.1f}MB freed")
    
    def _enforce_size_limit(self):
        """Remove LRU entries if size limit exceeded"""
        current_size_bytes = self.stats['current_size_mb'] * 1024 * 1024
        
        while current_size_bytes > self.max_size_bytes and self.cache:
            # Remove least recently used (first item in OrderedDict)
            key, entry = self.cache.popitem(last=False)  # FIFO = LRU in our usage
            current_size_bytes -= entry.estimated_size_mb * 1024 * 1024
            self.stats['evictions_lru'] += 1
            self.stats['current_size_mb'] -= entry.estimated_size_mb
            self.stats['total_entries'] -= 1
            
            # Explicitly delete tensors to free memory
            del entry.data
            del entry
            
            logger.info(f"🗑️ LRU EVICTED: {key[:8]}... (freed: {entry.estimated_size_mb:.1f}MB)")
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached video with LRU update"""
        with self._lock:
            self._cleanup_expired()  # Clean expired entries first
            
            if key in self.cache:
                # Cache hit: Update access time and move to end (most recent)
                entry = self.cache.pop(key)
                entry.last_accessed = time.time()
                entry.access_count += 1
                self.cache[key] = entry  # Move to end of OrderedDict
                
                self.stats['hits'] += 1
                return entry.data
            else:
                # Cache miss
                self.stats['misses'] += 1
                return None
    
    def put(self, key: str, video_info: Any):
        """Cache video with size and TTL management"""
        with self._lock:
            current_time = time.time()
            
            # Measure size estimation time for performance tuning
            size_estimation_start = time.time()
            estimated_size = self._estimate_tensor_size_mb(video_info)
            size_estimation_time = time.time() - size_estimation_start
            
            # Remove existing entry if present
            if key in self.cache:
                old_entry = self.cache.pop(key)
                self.stats['current_size_mb'] -= old_entry.estimated_size_mb
                self.stats['total_entries'] -= 1
            
            # Create new cache entry
            entry = CacheEntry(
                data=video_info,
                created_at=current_time,
                last_accessed=current_time,
                estimated_size_mb=estimated_size
            )
            
            # Add to cache (end of OrderedDict = most recent)
            self.cache[key] = entry
            self.stats['current_size_mb'] += estimated_size
            self.stats['total_entries'] += 1
            
            # Enforce limits
            self._cleanup_expired()
            self._enforce_size_limit()
            
            logger.info(f"💾 CACHED: {key[:8]}... ({estimated_size:.1f}MB, total: {self.stats['current_size_mb']:.1f}MB) | Size estimation: {size_estimation_time*1000:.1f}ms")
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        with self._lock:
            hit_rate = self.stats['hits'] / (self.stats['hits'] + self.stats['misses']) if (self.stats['hits'] + self.stats['misses']) > 0 else 0
            return {
                **self.stats,
                'hit_rate_percent': round(hit_rate * 100, 2),
                'max_size_gb': self.max_size_bytes / (1024**3),
                'ttl_minutes': self.ttl_seconds / 60,
                'utilization_percent': round((self.stats['current_size_mb'] * 1024**2) / self.max_size_bytes * 100, 2)
            }
    
    def clear(self):
        """Clear all cached entries and force garbage collection"""
        with self._lock:
            # Delete all entries explicitly before clearing
            for key, entry in list(self.cache.items()):
                del entry.data
                del entry
            
            self.cache.clear()
            self.stats = {
                'hits': 0,
                'misses': 0,
                'evictions_lru': 0,
                'evictions_ttl': 0,
                'current_size_mb': 0,
                'total_entries': 0
            }
            
            # Force garbage collection to free memory immediately
            import gc
            gc.collect()
            logger.info("🧹 Cache cleared and garbage collected")
    
    def shutdown(self):
        """Stop background cleanup thread (called on server shutdown)"""
        self._stop_cleanup.set()
        if self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5)
            logger.info("🛑 TTL cleanup thread stopped")

# Initialize caches (configuration loaded from config.py)
MODEL_CACHE = {}    # VRAM: {model_name: (net, feature_utils, seq_cfg)}
SMART_VIDEO_CACHE = SmartVideoCache(max_size_gb=VIDEO_CACHE_MAX_GB, ttl_minutes=VIDEO_CACHE_TTL_MIN)
CACHE_DIR = Path("./cache")  # Disk: temporary audio files
CACHE_DIR.mkdir(exist_ok=True)

# GPU Queue Management
GPU_SEMAPHORE = asyncio.Semaphore(1)  # Only 1 concurrent GPU inference at a time
active_requests = 0  # Currently running GPU inference
pending_requests = 0  # Waiting in queue

# Cache cleanup configuration
CACHE_RETENTION_HOURS = 2  # Delete audio files older than 2 hours
CLEANUP_INTERVAL_MINUTES = 30  # Run cleanup every 30 minutes

def cleanup_old_cache_files():
    """Remove audio files older than CACHE_RETENTION_HOURS"""
    try:
        current_time = time.time()
        retention_seconds = CACHE_RETENTION_HOURS * 3600
        
        for file_path in CACHE_DIR.glob("audio_*.flac"):
            if file_path.is_file():
                file_age = current_time - file_path.stat().st_mtime
                if file_age > retention_seconds:
                    file_path.unlink()
                    logger.info(f"Cleaned up old cache file: {file_path.name}")
    except Exception as e:
        logger.error(f"Cache cleanup error: {e}")

def schedule_cleanup():
    """Background thread for periodic cache cleanup"""
    while True:
        time.sleep(CLEANUP_INTERVAL_MINUTES * 60)
        cleanup_old_cache_files()

# Start cleanup thread on startup
cleanup_thread = threading.Thread(target=schedule_cleanup, daemon=True)
cleanup_thread.start()

def _get_gpu_overview():
    """
    Return GPU totals and per-process usage using pynvml (best-effort).
    
    Returns detailed GPU information including:
    - Total/used/free memory per GPU
    - List of processes using each GPU with PID and memory usage
    - Process names (when available)
    """
    if not PYNVML_AVAILABLE:
        return {"available": False, "note": "pynvml not installed (install: pip install nvidia-ml-py3)"}
    
    try:
        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()
        gpus = []
        
        for i in range(device_count):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            name = pynvml.nvmlDeviceGetName(h)
            
            total_mb = round(mem.total / 1024**2, 2)
            used_mb = round(mem.used / 1024**2, 2)
            free_mb = round(mem.free / 1024**2, 2)
            
            procs_list = []
            # Try to get compute processes (CUDA workloads)
            try:
                nv_procs = pynvml.nvmlDeviceGetComputeRunningProcesses(h)
            except Exception:
                # Fallback to graphics processes if compute fails
                try:
                    nv_procs = pynvml.nvmlDeviceGetGraphicsRunningProcesses(h)
                except Exception:
                    nv_procs = []
            
            for p in nv_procs:
                pid = getattr(p, "pid", None)
                used_proc_mb = None
                if hasattr(p, "usedGpuMemory"):
                    used_proc_mb = round(p.usedGpuMemory / 1024**2, 2)
                
                # Try to resolve PID -> process name (may fail in containers)
                proc_name = None
                proc_cmdline = None
                try:
                    if pid is not None:
                        proc = psutil.Process(pid)
                        proc_name = proc.name()
                        # Get command line to identify API processes
                        cmdline = proc.cmdline()
                        if len(cmdline) > 1:
                            proc_cmdline = ' '.join(cmdline[:3])  # First 3 args
                except Exception:
                    pass
                
                procs_list.append({
                    "pid": pid,
                    "process_name": proc_name,
                    "cmdline": proc_cmdline,
                    "used_mb": used_proc_mb
                })
            
            gpus.append({
                "index": i,
                "name": name,
                "total_mb": total_mb,
                "used_mb": used_mb,
                "free_mb": free_mb,
                "utilization_percent": round((used_mb / total_mb) * 100, 2) if total_mb > 0 else 0,
                "processes": procs_list
            })
        
        pynvml.nvmlShutdown()
        return {"available": True, "gpus": gpus}
        
    except Exception as e:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
        return {"available": False, "error": str(e)}


# ========== FASTAPI APPLICATION ==========
app = FastAPI(
    title="MMAudio Standalone API",
    description="High-performance video-to-audio generation API",
    version="1.0.0"
)

# Enable CORS for web requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

def get_cached_model(model_name: str = 'large_44k_v2', target_dtype = None) -> tuple[MMAudio, FeaturesUtils, ModelConfig]:
    """
    MODEL CACHE MECHANISM with dtype-aware caching
    
    Cache key now includes dtype to prevent mixed-precision issues.
    This allows caching both bfloat16 and float32 versions simultaneously.
    
    Example cache keys:
    - "large_44k_v2_torch.bfloat16"
    - "large_44k_v2_torch.float32"
    
    CACHE HIT (model already loaded with correct dtype):
    - Returns cached model from VRAM instantly
    
    CACHE MISS (first time loading model with this dtype):
    - Downloads model weights if needed (only once ever)
    - Loads PyTorch model into VRAM WITH CORRECT DTYPE
    - Initializes feature extraction utilities
    - Stores in MODEL_CACHE for future requests
    
    Memory Impact:
    - Both precisions cached = ~2x VRAM usage (e.g., 10GB bfloat16 + 18GB float32 = 28GB total)
    - Consider clearing cache if VRAM limited (use /cache/clear-all endpoint)
    """
    if target_dtype is None:
        target_dtype = dtype  # Default: bfloat16 (global)
    
    # Create dtype-aware cache key
    cache_key = f"{model_name}_{target_dtype}"
    
    # CACHE HIT: Return immediately from VRAM
    if cache_key in MODEL_CACHE:
        logger.info(f"🚀 CACHE HIT: Using cached model '{cache_key}' from VRAM")
        return MODEL_CACHE[cache_key]
    
    # CACHE MISS: Load model from disk into VRAM WITH CORRECT DTYPE
    logger.info(f"💾 CACHE MISS: Loading model '{model_name}' into VRAM with dtype {target_dtype}...")
    start_time = time.time()
    
    # Validate model exists
    if model_name not in all_model_cfg:
        raise ValueError(f'Unknown model variant: {model_name}')
    
    model: ModelConfig = all_model_cfg[model_name]
    model.download_if_needed()
    seq_cfg = model.seq_cfg

    # Load with TARGET DTYPE from the start (CRITICAL: weights loaded in correct precision)
    net: MMAudio = get_my_mmaudio(model.model_name).to(device, target_dtype).eval()
    net.load_weights(torch.load(model.model_path, map_location=device, weights_only=True))
    
    # Load feature extraction utilities with target dtype
    feature_utils = FeaturesUtils(tod_vae_ckpt=model.vae_path,
                                  synchformer_ckpt=model.synchformer_ckpt,
                                  enable_conditions=True,
                                  mode=model.mode,
                                  bigvgan_vocoder_ckpt=model.bigvgan_16k_path,
                                  need_vae_encoder=False)
    feature_utils = feature_utils.to(device, target_dtype).eval()
    
    load_time = time.time() - start_time
    logger.info(f"✅ Model '{cache_key}' loaded in {load_time:.2f}s and cached in VRAM")
    
    # Cache with dtype-aware key
    MODEL_CACHE[cache_key] = (net, feature_utils, seq_cfg)
    return net, feature_utils, seq_cfg

def load_video_optimized(video_path: Path, duration_sec: float):
    """
    SMART VIDEO CACHE MECHANISM:
    
    Features:
    - Content-Based Caching: Cache key based on video file content, not filename
    - LRU Eviction: Automatically removes least recently used videos when memory limit reached
    - TTL Expiry: Videos expire after configurable time (default: 90 minutes)
    - Size Tracking: Monitors actual memory usage with intelligent estimation
    - Thread-safe: Multiple concurrent requests handled safely
    - Statistics: Tracks hit rates, evictions, memory usage
    
    CACHE KEY GENERATION:
    - MD5 hash of: first_1MB_of_video + duration + file_size
    - Content-based: Same video content always produces same cache key
    - Duration-aware: Different durations create separate cache entries
    
    CACHE HIT:
    - Returns preprocessed video tensors instantly from RAM
    - Updates LRU order (moves to most recently used)
    - Works even if same video uploaded with different temporary filenames
    
    CACHE MISS:
    - Processes video through MMAudio pipeline
    - Estimates memory usage for smart eviction
    - Auto-evicts old/unused videos if memory limit exceeded
    """
    # Generate content-based cache key (first 1MB + duration + file size)
    try:
        file_size = video_path.stat().st_size
        with open(video_path, 'rb') as f:
            # Read first 1MB for content-based hashing (fast but unique)
            content_sample = f.read(1024 * 1024)  # 1MB sample
        
        # Create hash from content sample + duration + file size
        cache_key_data = f"{hashlib.md5(content_sample).hexdigest()}_{duration_sec}_{file_size}"
        cache_key = hashlib.md5(cache_key_data.encode()).hexdigest()
        
    except Exception as e:
        # Fallback to path-based caching if content reading fails
        logger.warning(f"Content-based caching failed, using path-based: {e}")
        cache_key = hashlib.md5(f"{video_path}_{duration_sec}_{video_path.stat().st_mtime}".encode()).hexdigest()
    
    # Try to get from smart cache
    cached_video = SMART_VIDEO_CACHE.get(cache_key)
    
    if cached_video is not None:
        # CACHE HIT: Return from smart cache
        logger.info(f"🚀 SMART CACHE HIT: '{video_path.name}' (key: {cache_key[:8]}...)")
        return cached_video
    
    # CACHE MISS: Process video and add to smart cache
    logger.info(f"💾 SMART CACHE MISS: Processing '{video_path.name}'...")
    start_time = time.time()
    
    # Process video using MMAudio's native function
    try:
        video_info = load_video(video_path, duration_sec)
        
        # Validate video_info
        if video_info is None:
            raise ValueError(f"Video loading returned None for '{video_path.name}'")
        
        # Check if video has frames
        if hasattr(video_info, 'frames') and len(video_info.frames) == 0:
            raise ValueError(f"Video '{video_path.name}' has no frames (duration: {duration_sec}s)")
            
    except Exception as e:
        logger.error(f"❌ Video loading failed for '{video_path.name}': {e}")
        logger.error(f"Video details - Duration: {duration_sec}s, Size: {video_path.stat().st_size} bytes")
        raise ValueError(f"Failed to load video '{video_path.name}': {str(e)}") from e
    
    load_time = time.time() - start_time
    logger.info(f"✅ Video '{video_path.name}' processed in {load_time:.2f}s")
    
    # Add to smart cache (handles size limits, TTL, LRU automatically)
    SMART_VIDEO_CACHE.put(cache_key, video_info)
    
    return video_info


# ========== API ENDPOINTS ==========
@app.get("/")
async def root():
    """API health check"""
    return {
        "message": "MMAudio Standalone API",
        "status": "running",
        "device": device,
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for API availability verification"""
    return {
        "status": "ok",
        "service": "MMAudio Standalone API",
        "device": device,
        "version": "1.0.0"
    }

@app.get("/models")
async def list_models():
    """List available MMAudio models"""
    return {
        "available_models": list(all_model_cfg.keys()),
        "loaded_models": list(MODEL_CACHE.keys())
    }

@app.get("/logs")
async def get_logs(limit: int = 100, level: Optional[str] = None):
    """
    Get recent log entries from the API server
    
    Parameters:
    - limit: Maximum number of log entries to return (default: 100, max: 500)
    - level: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
    - List of log entries with timestamp, level, message, and module
    
    Example:
    - GET /logs?limit=50
    - GET /logs?level=ERROR
    - GET /logs?limit=20&level=INFO
    """
    # Limit the number of entries
    limit = min(limit, LOG_BUFFER_SIZE)
    
    # Get logs from buffer
    logs = list(log_buffer)
    
    # Filter by level if specified
    if level:
        level_upper = level.upper()
        logs = [log for log in logs if log["level"] == level_upper]
    
    # Return most recent entries (reverse order so newest first)
    logs.reverse()
    return {
        "total_entries": len(logs),
        "returned_entries": min(limit, len(logs)),
        "buffer_size": LOG_BUFFER_SIZE,
        "filter_level": level.upper() if level else None,
        "logs": logs[:limit]
    }

@app.get("/logs/tail")
async def tail_logs(lines: int = 50):
    """
    Get recent logs in plain text format (like 'tail -f')
    
    Parameters:
    - lines: Number of most recent log lines to return (default: 50, max: 500)
    
    Returns:
    - Plain text with formatted log entries
    
    Usage:
    - curl http://localhost:8000/logs/tail
    - curl http://localhost:8000/logs/tail?lines=100
    """
    lines = min(lines, LOG_BUFFER_SIZE)
    
    # Get most recent logs
    logs = list(log_buffer)[-lines:]
    
    # Format as plain text
    text_output = []
    text_output.append("=" * 80)
    text_output.append(f"MMAudio API Logs (last {len(logs)} entries)")
    text_output.append("=" * 80)
    text_output.append("")
    
    for log_entry in logs:
        text_output.append(f"[{log_entry['timestamp']}] {log_entry['level']:8} | {log_entry['message']}")
    
    text_output.append("")
    text_output.append("=" * 80)
    
    return StreamingResponse(
        iter(["\n".join(text_output)]),
        media_type="text/plain",
        headers={
            "Content-Disposition": "inline"
        }
    )


@app.get("/cache/stats")
async def get_cache_stats():
    """Get comprehensive cache statistics and system memory info (with real GPU monitoring)"""
    # System memory info
    memory = psutil.virtual_memory()
    
    # Current process GPU usage via torch (this process only)
    torch_gpu = {}
    if torch.cuda.is_available():
        try:
            torch_gpu = {
                "this_process_allocated_mb": round(torch.cuda.memory_allocated() / 1024**2, 2),
                "this_process_reserved_mb": round(torch.cuda.memory_reserved() / 1024**2, 2),
                "device_count": torch.cuda.device_count(),
                "device_name": torch.cuda.get_device_name(0) if torch.cuda.device_count() > 0 else None
            }
        except Exception as e:
            torch_gpu = {"error": str(e)}
    else:
        torch_gpu = {"available": False}
    
    # Global GPU overview using pynvml (system-wide, all processes)
    gpu_overview = _get_gpu_overview()
    
    return {
        "video_cache": SMART_VIDEO_CACHE.get_stats(),
        "model_cache": {
            "loaded_models": len(MODEL_CACHE),
            "model_names": list(MODEL_CACHE.keys())
        },
        "system_memory": {
            "total_gb": round(memory.total / (1024**3), 2),
            "available_gb": round(memory.available / (1024**3), 2),
            "used_gb": round(memory.used / (1024**3), 2),
            "usage_percent": memory.percent
        },
        "gpu_memory": {
            "torch_process_view": torch_gpu,
            "system_view": gpu_overview,
            "note": "torch_process_view = this API process only | system_view = all GPUs + all processes (requires pynvml)"
        },
        "cache_config": {
            "video_cache_max_gb": VIDEO_CACHE_MAX_GB,
            "video_cache_ttl_minutes": VIDEO_CACHE_TTL_MIN
        }
    }

@app.get("/queue/status")
async def get_queue_status():
    """Get GPU request queue status"""
    return {
        "queue_enabled": True,
        "pending_requests": pending_requests,
        "active_requests": active_requests,
        "max_concurrent": GPU_SEMAPHORE._value,
        "queue_strategy": "FIFO (First In First Out)"
    }


@app.post("/cache/clear")
async def clear_cache():
    """Clear video cache (keeps model cache for performance)"""
    SMART_VIDEO_CACHE.clear()
    return {
        "message": "Video cache cleared successfully",
        "model_cache_preserved": True
    }

@app.post("/cache/clear-all")
async def clear_all_cache():
    """Clear both video and model cache (full reset with explicit memory cleanup)"""
    import gc
    
    # Clear video cache (already has proper cleanup with gc)
    SMART_VIDEO_CACHE.clear()
    
    # Clear model cache WITH EXPLICIT DELETION
    logger.info(f"Clearing {len(MODEL_CACHE)} cached models...")
    for model_name, (net, feature_utils, seq_cfg) in list(MODEL_CACHE.items()):
        logger.info(f"Deleting model '{model_name}' from RAM...")
        # Explicitly delete PyTorch models to free RAM
        del net
        del feature_utils
        del seq_cfg
    
    MODEL_CACHE.clear()
    
    # Force garbage collection (multiple passes for thorough cleanup)
    logger.info("Running garbage collection...")
    collected_objects = 0
    for i in range(3):
        collected = gc.collect()
        collected_objects += collected
        logger.info(f"GC pass {i+1}/3: collected {collected} objects")
    
    # Clear GPU memory
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        logger.info("GPU cache cleared")
    
    # Get memory info after cleanup
    process = psutil.Process()
    mem_after = process.memory_info()
    
    logger.info(f"✅ All caches cleared | RAM after: {mem_after.rss / 1024**3:.2f} GB")
    
    return {
        "message": "All caches cleared successfully",
        "gpu_memory_cleared": torch.cuda.is_available(),
        "gc_objects_collected": collected_objects,
        "ram_after_gb": round(mem_after.rss / 1024**3, 2),
        "note": "Models will need to be reloaded on next request (30-60s delay)"
    }

def cleanup_file_after_delay(file_path: Path, delay_minutes: int = 5):
    """Delete file after specified delay (for immediate cleanup after download)"""
    def delayed_cleanup():
        time.sleep(delay_minutes * 60)
        try:
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Immediate cleanup: {file_path.name}")
        except Exception as e:
            logger.error(f"Immediate cleanup error: {e}")
    
    threading.Thread(target=delayed_cleanup, daemon=True).start()

@app.post("/generate")
async def generate_audio(
    background_tasks: BackgroundTasks,
    video: Optional[UploadFile] = File(None),  # Optional for T2A mode
    prompt: str = Form(""),
    negative_prompt: str = Form(""),
    seed: int = Form(42),
    duration: Optional[float] = Form(None),
    model_name: str = Form("large_44k_v2"),
    num_steps: int = Form(25),
    cfg_strength: float = Form(4.5),
    output_format: str = Form("flac"),  # "flac" or "wav"
    full_precision: bool = Form(False)  # NEW: Use float32 instead of bfloat16
):
    """
    Generate audio from video (V2A) or text only (T2A).
    
    Args:
        video: Video file (optional). If None, uses T2A mode (text-to-audio)
        duration: Duration in seconds (required for T2A, auto-detected for V2A)
        output_format: "flac" (default, lossless compression) or "wav" (uncompressed PCM)
                      Use "wav" for Pro Tools PTSL compatibility (avoids client-side conversion)
        full_precision: Use torch.float32 (high quality, slower) instead of torch.bfloat16 (default, faster)
    """
    # Track request in queue immediately (before any processing)
    global pending_requests
    pending_requests += 1
    logger.info(f"🔄 Request received (pending: {pending_requests})")
    
    try:
        # Determine mode: T2A (text-only) or V2A (video-to-audio)
        is_t2a_mode = video is None
        
        if is_t2a_mode:
            # ========== T2A MODE: Text-to-Audio (no video input) ==========
            logger.info("🎵 T2A MODE: Text-to-audio generation (no video)")
            
            # Duration is REQUIRED for T2A mode
            if duration is None:
                raise HTTPException(status_code=400, detail="duration is required for T2A mode (text-only generation). Specify duration in seconds (e.g., 8.0)")
            
            # Validate duration limits for T2A
            if duration < 4:
                raise HTTPException(status_code=400, detail=f"Duration too short: {duration:.2f}s (minimum 4s for T2A)")
            if duration > 12:
                raise HTTPException(status_code=400, detail=f"Duration too long: {duration:.2f}s (maximum 12s for T2A)")
            
            logger.info(f"T2A parameters: duration={duration:.2f}s, prompt='{prompt}', seed={seed}")
            
            # T2A: No video processing needed
            clip_frames = None
            sync_frames = None
            tmp_video_path = None
            
        else:
            # ========== V2A MODE: Video-to-Audio (with video input) ==========
            logger.info("🎬 V2A MODE: Video-to-audio generation")
            
            # Save uploaded video to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp_file:
                content = await video.read()
                tmp_file.write(content)
                tmp_video_path = Path(tmp_file.name)
            
            # Frame check: disabled by default. Set VIDEO_FRAME_CHECK=1/true/yes/on to enable quick first-frame decode.
            
            validation_start = time.time()
            try:
                metadata_start = time.time()
                with av.open(tmp_video_path) as container:
                    if not container.streams.video:
                        raise HTTPException(status_code=400, detail="Video file has no video stream")
                    stream = container.streams.video[0]
                    # Prefer stream.duration if available
                    try:
                        duration_actual = float(stream.duration * stream.time_base)
                    except Exception:
                        # Fallback to container duration in seconds
                        duration_actual = float(container.duration / av.time_base) if getattr(container, 'duration', None) else 0.0

                    metadata_time = time.time() - metadata_start
                    logger.info(f"📊 Metadata check: {metadata_time*1000:.1f}ms | Video duration: {duration_actual:.2f}s")

                    # Quick decode check (first frame) if enabled
                    if VIDEO_FRAME_CHECK:
                        frame_check_start = time.time()
                        frame_found = False
                        # Demux + decode until first frame or until a small number of packets checked
                        for packet in container.demux(stream):
                            for frame in packet.decode():
                                frame_found = True
                                break
                            if frame_found:
                                break
                        frame_check_time = time.time() - frame_check_start
                        
                        if not frame_found:
                            raise HTTPException(status_code=400, detail=f"Video appears to have no decodable frames (duration: {duration_actual:.2f}s)")
                        
                        logger.info(f"✅ Frame decode check: {frame_check_time*1000:.1f}ms | First frame decoded successfully")

            except HTTPException:
                # Re-raise FastAPI HTTPExceptions
                raise
            except Exception as e:
                logger.error(f"Error while inspecting uploaded video: {e}")
                raise HTTPException(status_code=400, detail=f"Failed to read video metadata: {e}")
            
            validation_total_time = time.time() - validation_start
            logger.info(f"⏱️  Total validation time: {validation_total_time*1000:.1f}ms")

            # If client provided a duration, warn if it differs significantly and prefer the actual
            if duration is not None:
                if abs(duration - duration_actual) > 0.5:
                    logger.warning(f"Client-supplied duration ({duration:.2f}s) differs from file ({duration_actual:.2f}s); using file value")
            duration = duration_actual

            # Validate duration limits (use file-derived duration)
            if duration < 4:
                raise HTTPException(status_code=400, detail=f"Video too short: {duration:.2f}s (minimum 4s)")
            if duration > 12:
                raise HTTPException(status_code=400, detail=f"Video too long: {duration:.2f}s (maximum 12s)")
            
            # Load and process video using MMAudio's native function
            video_info = load_video_optimized(tmp_video_path, duration)
            
            # Exact logic from demo.py for video processing
            clip_frames = video_info.clip_frames
            sync_frames = video_info.sync_frames
            duration = video_info.duration_sec
            
            # Apply demo.py logic: unsqueeze for batch dimension
            clip_frames = clip_frames.unsqueeze(0)
            sync_frames = sync_frames.unsqueeze(0)
        
        # ========== COMMON: Model loading and generation setup ==========
        
        # Determine target dtype for this request
        target_dtype = torch.float32 if full_precision else dtype  # dtype = bfloat16 (global)
        
        if full_precision:
            logger.info("🔬 Using full precision mode (float32) - higher quality, slower")
        else:
            logger.info(f"⚡ Using default precision ({dtype}) - faster, lower memory")
        
        # Load model with correct dtype from the start (dtype-aware caching)
        # This ensures weights are loaded in the correct precision
        net, feature_utils, seq_cfg = get_cached_model(model_name, target_dtype=target_dtype)
        
        # CRITICAL: Convert video tensors to target dtype (only for V2A mode)
        # Cached video_info is in bfloat16, but we need float32 for full precision
        if not is_t2a_mode and clip_frames.dtype != target_dtype:
            logger.info(f"Converting video tensors from {clip_frames.dtype} to {target_dtype}...")
            clip_frames = clip_frames.to(target_dtype)
            sync_frames = sync_frames.to(target_dtype)
        
        # Update sequence configuration (from demo.py)
        seq_cfg.duration = duration
        net.update_seq_lengths(seq_cfg.latent_seq_len, seq_cfg.clip_seq_len, seq_cfg.sync_seq_len)
        
        # Setup generation exactly like demo.py
        rng = torch.Generator(device=device)
        rng.manual_seed(seed)
        fm = FlowMatching(min_sigma=0, inference_mode='euler', num_steps=num_steps)
        
        logger.info(f"Generating audio: prompt='{prompt}', negative_prompt='{negative_prompt}', duration={duration:.2f}s, seed={seed}")
        start_time = time.time()

        # GPU Queue Management: Acquire semaphore before GPU inference
        global active_requests
        logger.info(f"⏳ Waiting for GPU lock (pending: {pending_requests}, active: {active_requests})")
        
        async with GPU_SEMAPHORE:
            pending_requests -= 1
            active_requests += 1
            logger.info(f"🔒 GPU lock acquired (pending: {pending_requests}, active: {active_requests})")
            
            try:
                # Generate audio with no_grad (like demo.py)
                # Note: generate() function returns audio-only by default (no video composite)
                with torch.no_grad():
                    audios = generate(clip_frames,
                                      sync_frames, [prompt],
                                      negative_text=[negative_prompt] if negative_prompt else None,
                                      feature_utils=feature_utils,
                                      net=net,
                                      fm=fm,
                                      rng=rng,
                                      cfg_strength=cfg_strength)
            finally:
                active_requests -= 1
                logger.info(f"🔓 GPU lock released (pending: {pending_requests}, active: {active_requests})")

        generation_time = time.time() - start_time
        logger.info(f"Audio generated in {generation_time:.2f}s")

        # Save audio exactly like demo.py
        audio = audios.float().cpu()[0]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Validate output format
        output_format = output_format.lower()
        if output_format not in ["flac", "wav"]:
            raise HTTPException(status_code=400, detail=f"Invalid output_format: {output_format}. Must be 'flac' or 'wav'")
        
        # Upsample to 48kHz if needed (Pro Tools standard sample rate)
        target_sample_rate = 48000
        if seq_cfg.sampling_rate != target_sample_rate:
            logger.info(f"Upsampling audio from {seq_cfg.sampling_rate}Hz to {target_sample_rate}Hz...")
            resample_start = time.time()
            
            resampler = T.Resample(
                orig_freq=seq_cfg.sampling_rate,
                new_freq=target_sample_rate,
                dtype=audio.dtype
            )
            audio = resampler(audio)
            
            resample_time = time.time() - resample_start
            logger.info(f"Resampled to {target_sample_rate}Hz in {resample_time:.2f}s")
        else:
            logger.info(f"Audio already at {target_sample_rate}Hz, no resampling needed")
        
        # Generate descriptive filename: {prompt_snippet}_{seed}_{model(size)}_{timestamp}.ext
        # Example: footsteps_concrete_42_mmaudio(L)_20231122_142533.wav
        # Sanitize prompt for filename (max 30 chars, alphanumeric + spaces -> underscores)
        def sanitize_filename(text: str, max_length: int = 30) -> str:
            """Convert text to filesystem-safe filename component"""
            import re
            # Take first max_length chars
            text = text[:max_length]
            # Replace spaces with underscores, remove non-alphanumeric (except underscores/hyphens)
            text = re.sub(r'[^\w\s-]', '', text)
            text = re.sub(r'[-\s]+', '_', text)
            return text.strip('_').lower()
        
        def format_model_name(model_name: str) -> str:
            """Format model name as: provider(size) - e.g., mmaudio(L), mmaudio(M), mmaudio(S)"""
            model_lower = model_name.lower()
            
            if 'large' in model_lower:
                size = 'L'
            elif 'medium' in model_lower:
                size = 'M'
            elif 'small' in model_lower:
                size = 'S'
            else:
                size = 'X'  # Unknown size
            
            # Assume MMAudio for now (can be extended for other providers)
            return f"mmaudio({size})"
        
        prompt_snippet = sanitize_filename(prompt if prompt else "generated")
        model_formatted = format_model_name(model_name)
        
        # Save as FLAC first (like demo.py)
        flac_filename = f"{prompt_snippet}_{seed}_{model_formatted}_{timestamp}.flac"
        flac_path = CACHE_DIR / flac_filename
        torchaudio.save(flac_path, audio, target_sample_rate)
        logger.info(f"Audio file saved as {flac_path}")
        
        # Convert to WAV if requested (for Pro Tools PTSL compatibility)
        if output_format == "wav":
            logger.info("Converting FLAC to WAV (24-bit PCM) for Pro Tools compatibility...")
            convert_start = time.time()
            
            wav_filename = f"{prompt_snippet}_{seed}_{model_formatted}_{timestamp}.wav"
            wav_path = CACHE_DIR / wav_filename
            
            # Use soundfile for reliable 24-bit PCM (torchaudio has encoding parameter issues)
            try:
                import soundfile as sf
                waveform, sample_rate = torchaudio.load(flac_path)
                # Convert to numpy for soundfile (transpose for correct shape)
                audio_np = waveform.cpu().numpy().T  # Shape: (samples, channels)
                sf.write(str(wav_path), audio_np, sample_rate, subtype='PCM_24')
                logger.info(f"✅ WAV saved: 24-bit PCM, {sample_rate}Hz, {waveform.shape[0]}ch")
            except ImportError:
                # Fallback to torchaudio (may produce 16-bit on some systems)
                logger.warning("soundfile not available, using torchaudio (may not be 24-bit)")
                waveform, sample_rate = torchaudio.load(flac_path)
                torchaudio.save(wav_path, waveform, sample_rate)
                logger.info(f"⚠️  WAV saved with torchaudio (bit depth may vary)")
            
            convert_time = time.time() - convert_start
            logger.info(f"Converted to WAV in {convert_time:.2f}s")
            
            # Use WAV as final output, schedule both files for cleanup
            final_path = wav_path
            final_filename = wav_filename
            media_type = "audio/wav"
            
            cleanup_file_after_delay(flac_path, delay_minutes=5)
            cleanup_file_after_delay(wav_path, delay_minutes=5)
        else:
            # Use FLAC as final output
            final_path = flac_path
            final_filename = flac_filename
            media_type = "audio/flac"
            
            cleanup_file_after_delay(flac_path, delay_minutes=5)

        # Clean up temporary video file (only in V2A mode)
        if tmp_video_path is not None:
            tmp_video_path.unlink()
        
        return FileResponse(
            final_path,
            media_type=media_type,
            filename=final_filename,
            headers={
                "Content-Disposition": f'attachment; filename="{final_filename}"',
                "X-Generation-Time": str(generation_time),
                "X-Duration": str(duration),  # Works for both T2A and V2A
                "X-Seed": str(seed),
                "X-Sample-Rate": str(target_sample_rate),
                "X-Output-Format": output_format,
                "X-Mode": "T2A" if is_t2a_mode else "V2A"
            }
        )
        
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # CRITICAL: Always decrement pending_requests, even on error
        # This prevents failed requests from staying in queue forever
        if pending_requests > 0:
            pending_requests -= 1
            logger.debug(f"📉 Request completed, pending_requests now: {pending_requests}")


# ========== MEMORY PROFILING ENDPOINT ==========
@app.get("/memory/profile")
async def get_memory_profile():
    """Get detailed memory profiling information"""
    import gc
    from collections import Counter
    
    try:
        # Collect garbage first
        gc.collect()
        
        # Process memory
        process = psutil.Process()
        mem_info = process.memory_info()
        
        # Count objects by type
        obj_counts = Counter()
        obj_sizes = {}
        
        for obj in gc.get_objects():
            obj_type = type(obj).__name__
            obj_counts[obj_type] += 1
            
            try:
                size = sys.getsizeof(obj)
                if obj_type not in obj_sizes:
                    obj_sizes[obj_type] = 0
                obj_sizes[obj_type] += size
            except:
                pass
        
        # Sort by size
        top_objects = sorted(obj_sizes.items(), key=lambda x: x[1], reverse=True)[:30]
        
        result = {
            "process_memory": {
                "rss_mb": mem_info.rss / 1024 / 1024,
                "vms_mb": mem_info.vms / 1024 / 1024,
                "rss_gb": mem_info.rss / 1024 / 1024 / 1024,
            },
            "top_objects": [
                {
                    "type": obj_type,
                    "total_size_mb": size / 1024 / 1024,
                    "count": obj_counts[obj_type],
                    "avg_size_bytes": size / obj_counts[obj_type] if obj_counts[obj_type] > 0 else 0
                }
                for obj_type, size in top_objects
            ],
            "tracemalloc": None
        }
        
        # Tracemalloc info
        if tracemalloc.is_tracing():
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')[:20]
            
            result["tracemalloc"] = [
                {
                    "file": str(stat.traceback[0].filename),
                    "line": stat.traceback[0].lineno,
                    "size_mb": stat.size / 1024 / 1024,
                    "count": stat.count
                }
                for stat in top_stats
            ]
        
        return result
        
    except Exception as e:
        logger.error(f"Memory profiling failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== RUN APPLICATION ==========
if __name__ == "__main__":
    # Enable memory tracking for debugging
    if ENABLE_TRACEMALLOC:
        tracemalloc.start()
        logger.info("tracemalloc enabled for memory profiling")
    
    logger.info(f"Starting MMAudio Standalone API on {API_HOST}:{API_PORT}...")
    logger.info(f"Cache: {VIDEO_CACHE_MAX_GB}GB max, {VIDEO_CACHE_TTL_MIN}min TTL")
    logger.info(f"Device: {device}, Dtype: {dtype}")
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level=LOG_LEVEL)
