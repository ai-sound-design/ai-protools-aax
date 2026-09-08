#!/usr/bin/env python3
"""
Memory Profiler for MMAudio API
Tracks which Python objects are consuming RAM
"""

import gc
import sys
import psutil
import tracemalloc
from collections import Counter
from datetime import datetime
import time

def get_memory_usage():
    """Get current memory usage in MB"""
    process = psutil.Process()
    return process.memory_info().rss / 1024 / 1024

def get_top_objects(limit=20):
    """Get the top memory-consuming Python objects"""
    gc.collect()
    
    # Count objects by type
    obj_counts = Counter()
    obj_sizes = {}
    
    for obj in gc.get_objects():
        obj_type = type(obj).__name__
        obj_counts[obj_type] += 1
        
        # Estimate size
        try:
            size = sys.getsizeof(obj)
            if obj_type not in obj_sizes:
                obj_sizes[obj_type] = 0
            obj_sizes[obj_type] += size
        except:
            pass
    
    # Sort by total size
    sorted_types = sorted(obj_sizes.items(), key=lambda x: x[1], reverse=True)
    
    return sorted_types[:limit], obj_counts

def format_size(bytes_size):
    """Format bytes to human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.2f} TB"

def analyze_tracemalloc(top_n=10):
    """Use tracemalloc to find where memory is allocated"""
    if not tracemalloc.is_tracing():
        print("⚠️  tracemalloc not enabled. Enable it in main.py startup.")
        return []
    
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')
    
    return top_stats[:top_n]

def main():
    print("=" * 80)
    print(f"Memory Profile Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()
    
    # Overall memory usage
    mem_mb = get_memory_usage()
    print(f"📊 Total Process Memory: {mem_mb:.2f} MB ({mem_mb/1024:.2f} GB)")
    print()
    
    # Top objects by size
    print("🔍 Top 20 Object Types by Total Size:")
    print("-" * 80)
    top_objects, obj_counts = get_top_objects(20)
    
    for i, (obj_type, total_size) in enumerate(top_objects, 1):
        count = obj_counts[obj_type]
        avg_size = total_size / count if count > 0 else 0
        print(f"{i:2d}. {obj_type:30s} | Total: {format_size(total_size):>12s} | "
              f"Count: {count:>8,d} | Avg: {format_size(avg_size):>10s}")
    
    print()
    
    # Tracemalloc analysis
    print("🎯 Top 10 Memory Allocations (tracemalloc):")
    print("-" * 80)
    
    top_stats = analyze_tracemalloc(10)
    if top_stats:
        for i, stat in enumerate(top_stats, 1):
            print(f"{i:2d}. {stat.traceback.format()[0]}")
            print(f"    Size: {format_size(stat.size)} | Count: {stat.count:,d}")
            print()
    else:
        print("⚠️  Enable tracemalloc in main.py to see allocation sources")
        print("    Add at startup: tracemalloc.start()")
        print()
    
    # GPU Memory (if available)
    try:
        import torch
        if torch.cuda.is_available():
            print("🎮 GPU Memory (CUDA):")
            print("-" * 80)
            allocated = torch.cuda.memory_allocated() / 1024**3
            reserved = torch.cuda.memory_reserved() / 1024**3
            print(f"Allocated: {allocated:.2f} GB")
            print(f"Reserved:  {reserved:.2f} GB")
            print(f"Cached:    {reserved - allocated:.2f} GB")
            print()
    except:
        pass
    
    # Cache information (if available)
    try:
        import requests
        response = requests.get("http://localhost:8000/cache/stats", timeout=5)
        if response.status_code == 200:
            cache_data = response.json()
            print("💾 Video Cache Stats:")
            print("-" * 80)
            video_cache = cache_data.get('video_cache', {})
            print(f"Current Size: {video_cache.get('current_size_mb', 0):.2f} MB")
            print(f"Total Entries: {video_cache.get('total_entries', 0)}")
            print(f"Hits: {video_cache.get('hits', 0)} | Misses: {video_cache.get('misses', 0)}")
            print(f"Evictions (LRU): {video_cache.get('evictions_lru', 0)} | Evictions (TTL): {video_cache.get('evictions_ttl', 0)}")
            print()
    except:
        pass
    
    print("=" * 80)
    print("✅ Profile complete")
    print("=" * 80)

if __name__ == "__main__":
    main()
