#!/usr/bin/env python3
"""
Parallel API VRAM Stress Test

Tests TRUE parallel inference on a single API (when Semaphore > 1).
Monitors VRAM and queue status to verify parallel execution.

Usage:
    # Test with default settings (2 parallel requests per API)
    python3 test_concurrent_vram.py
    
    # Test with custom parallelism
    python3 test_concurrent_vram.py --parallel 3
    
    # Test only MMAudio
    python3 test_concurrent_vram.py --mmaudio-only --parallel 2
"""

import asyncio
import aiohttp
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List
import sys
import argparse


# Configuration
MMAUDIO_URL = "https://mmaudio.example.com"
HYVF_URL = "https://hyvf.example.com"
MONITORING_INTERVAL = 2.0  # seconds between VRAM checks
QUEUE_CHECK_INTERVAL = 1.0  # seconds between queue status checks

# Test videos - using short clips from customMicroFoleyTestSet
TEST_VIDEOS = {
    "mmaudio": "../model-tests/data/customMicroFoleyTestSet/noSound/test_door.mp4",
    "hyvf": "../model-tests/data/customMicroFoleyTestSet/noSound/test_footstepsPavement.mp4",
}


@dataclass
class QueueSnapshot:
    """Queue status at a point in time"""
    timestamp: float
    active_requests: int
    pending_requests: int
    max_concurrent: int
    
    @property
    def is_parallel(self) -> bool:
        """True if multiple requests are running in parallel"""
        return self.active_requests > 1
    
    def __str__(self):
        parallel_indicator = "🔥 PARALLEL" if self.is_parallel else "🔒 Sequential"
        return f"{parallel_indicator}: active={self.active_requests}, pending={self.pending_requests}"


@dataclass
class VRAMSnapshot:
    timestamp: float
    allocated_mb: float
    reserved_mb: float
    api_name: str
    
    def __str__(self):
        return f"{self.api_name}: {self.allocated_mb:.0f} MB allocated, {self.reserved_mb:.0f} MB reserved"


@dataclass
class TestResult:
    api_name: str
    video_name: str
    request_id: int  # Identify which parallel request this is
    duration: float
    success: bool
    vram_snapshots:
    
    @property
    def was_parallel(self) -> bool:
        """Check if this request ran in parallel with others"""
        return any(s.is_parallel for s in self.queue_snapshots)
    
    @property
    def max_parallel(self) -> int:
        """Maximum number of parallel requests during this execution"""
        return max((s.active_requests for s in self.queue_snapshots), default=0) List[VRAMSnapshot] = field(default_factory=list)
    queue_snapshots: List[QueueSnapshot] = field(default_factory=list)
    error: Optional[str] = None
    
    @property
    def vram_before(self) -> Optional[float]:
        return self.vram_snapshots[0].allocated_mb if self.vram_snapshots else None
    
    @property
    def vram_after(self) -> Optional[float]:
        return self.vram_snapshots[-1].allocated_mb if self.vram_snapshots else None
    
    @property
    def vram_pqueue_status(session: aiohttp.ClientSession, api_url: str) -> QueueSnapshot:
    """Get current queue status from API"""
    try:
        async with session.get(f"{api_url}/queue/status", timeout=5) as resp:
            if resp.status != 200:
                return QueueSnapshot(time.time(), 0, 0, 1)
            
            data = await resp.json()
            return QueueSnapshot(
                timestamp=time.time(),
                active_requests=data.get("active_requests", 0),
                pending_requests=data.get("pending_requests", 0),
                max_concurrent=data.get("max_concurrent", 1)
            )
    except Exception as e:
        print(f"⚠️  Error getting queue status: {e}")
        return QueueSnapshot(time.time(), 0, 0, 1)


async def monitor_queue_continuously(session: aiohttp.ClientSession,
                                    api_url: str,
                                    snapshots: List[QueueSnapshot],
                                    stop_event: asyncio.Event):
    """Monitor queue status to verify parallel execution"""
    while not stop_event.is_set():
        snapshot = await get_queue_status(session, api_url)
        snapshots.append(snapshot)
        
        # Only print if there's activity
        if snapshot.active_requests > 0 or snapshot.pending_requests > 0:
            print(f"      🔍 Queue: {snapshot}")
        
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=QUEUE_CHECK_INTERVAL)
        except asyncio.TimeoutError:
            continue


async def get_vram_usage(session: aiohttp.ClientSession, api_url: str) -> VRAMSnapshot:
    """Poll /cache/stats endpoint for VRAM usage"""
    try:
        async with session.get(f"{api_url}/cache/stats", timeout=5) as resp:
            if resp.status != 200:
                return VRAMSnapshot(time.time(), 0.0, 0.0, api_url.split('/')[-1])
            
            stats = await resp.json()
            torch_view = stats["gpu_memory"]["torch_process_view"]
            
            return VRAMSnapshot(
                timestamp=time.time(),
                allocated_mb=torch_view["this_process_allocated_mb"],
                reserved_mb=torch_view["this_process_reserved_mb"],
                api_name=api_url.split('/')[-1]
            )
    except Exception as e:
        print(f"⚠️  Error polling VRAM: {e}")
        return VRAMSnapshot(time.time(), 0.0, 0.0, api_url.split('/')[-1])


async def monitor_vram_continuously(session: aiohttp.ClientSession, 
                                   api_url: str, 
                                   snapshots: List[VRAMSnapshot],
                                   stop_event: asyncio.Event):
    """Background task to continuously monitor VRAM during inference"""
    while not stop_event.is_set():
        snapshot = await get_vram_usage(session, api_url)
        snapshots.append(snapshot)
        print(f"   📊 {snapshot}")
        
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=MONITORING_INTERVAL)
        except asyncio.TimeoutError:
            continue


async def send_request(session: aiohttp.ClientSession, 
                      api_url: str, 
                      video_path: str, 
                      params: dict,
                      request_id: int,
                      shared_queue_snapshots: List[QueueSnapshot]) -> TestResult:
    """Send single API request with monitoring"""
    
    api_name = "MMAudio" if "mmaudio" in api_url.lower() else "HunyuanVideo-Foley"
    video_name = Path(video_path).name
    
    print(f"\n   🚀 Request #{request_id}: {api_name} - {video_name}")
    
    # Initialize result
    vram_snapshots = []
    start_time = time.time()
    
    # Prepare request
    data = aiohttp.FormData()
    
    # Add video file
    with open(video_path, 'rb') as f:
        data.add_field('video', f, 
                      filename=Path(video_path).name, 
                      content_type='video/mp4')
        
        # Add parameters
        for key, value in params.items():
            data.add_field(key, str(value))
        
        # Send generation request
        try:
            print(f"      ⏳ Sending request...")
            async with session.post(f"{api_url}/generate", data=data, timeout=600) as resp:
                audio_data = await resp.read()
                success = resp.status == 200
                error = None if success else f"HTTP {resp.status}"
                
                if success:
                    print(f"      ✅ Completed ({len(audio_data)} bytes)")
                else:
                    print(f"      ❌ Failed: {error}")
        except Exception as e:
            success = False
            error = str(e)
            print(f"      ❌ Exception: {error}")
    
    duration = time.time() - start_time
    print(f"      ⏱️  Duration: {duration:.1f}s")
    
    return TestResult(
        api_name=api_name,
        video_name=video_name,
        request_id=request_id,
        duration=duration,
        success=success,
        vram_snapshots=vram_snapshots,
        queue_snapshots=shared_queue_snapshots.copy(),  # Copy shared snapshots
        error=error
    )


def get_default_params(api_url: str) -> dict:
    """Get default parameters based on API"""
    if "mmaudio" in api_url.lower():
        return {
            "prompt": "door opening",
            "negative_prompt": "voices, music",
            "seed": 42,
            "num_steps": 25,
            "output_format": "wav",
        }
    else:  # HunyuanVideo-Foley
        return {
            "prompt": "footsteps",
            "negative_prompt": "voices, music",
            "seed": 0,
            "model_size": "xxl",
            "num_steps": 50,
            "output_format": "wav",
        }


async def test_parallel_api(api_url: str, 
                           video_path: str, 
                           num_parallel: int,
                           session: aiohttp.ClientSession) -> List[TestResult]:
    """Test parallel execution on a single API"""
    
    api_name = "MMAudio" if "mmaudio" in api_url.lower() else "HunyuanVideo-Foley"
    
    print(f"\n{'='*80}")
    print(f"🔥 Testing {api_name} with {num_parallel} PARALLEL requests")
    print(f"{'='*80}")
    
    # Check initial queue configuration
    initial_queue = await get_queue_status(session, api_url)
    print(f"\n📋 Queue Configuration:")
    print(f"   Max Concurrent: {initial_queue.max_concurrent}")
    print(f"   Expected Behavior: {'✅ TRUE PARALLEL' if initial_queue.max_concurrent >= num_parallel else '⚠️  SEQUENTIAL (Semaphore too low)'}")
    
    if initial_queue.max_concurrent < num_parallel:
        print(f"\n⚠️  WARNING: API max_concurrent={initial_queue.max_concurrent} < requested parallel={num_parallel}")
        print(f"   Requests will be queued, not truly parallel!")
        print(f"   Increase GPU_SEMAPHORE in the API to asyncio.Semaphore({num_parallel})")
    
    # Get initial VRAM
    initial_vram = await get_vram_usage(session, api_url)
    print(f"\n📊 Initial VRAM: {initial_vram.allocated_mb:.0f} MB")
    
    # Shared queue snapshots (all requests will copy this)
    shared_queue_snapshots = []
    
    # Start background monitoring
    stop_event = asyncio.Event()
    
    vram_monitor = asyncio.create_task(
        monitor_vram_continuously(session, api_url, [], stop_event)
    )
    queue_monitor = asyncio.create_task(
        monitor_queue_continuously(session, api_url, shared_queue_snapshots, stop_event)
    )
    
    # Prepare all requests
    params = get_default_params(api_url)
    
    print(f"\n⚡ Launching {num_parallel} requests SIMULTANEOUSLY...")
    start_time = time.time()
    
    # Send ALL requests at the SAME time
    tasks = [
        send_request(session, api_url, video_path, params, i+1, shared_queue_snapshots)
        for i in range(num_parallel)
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    results = [r for r in results if isinstance(r, TestResult)]
    
    total_time = time.time() - start_time
    
    # Stop monitoring
    stop_event.set()
    await vram_monitor
    await queue_monitor
    
    # Get final VRAM
    final_vram = await get_vram_usage(session, api_url)
    
    # Analyze results
    print(f"\n{'='*80}")
    print(f"📊 {api_name} Results")
    print(f"{'='*80}")
    print(f"\nTotal Time: {total_time:.1f}s")
    print(f"VRAM Before: {initial_vram.allocated_mb:.0f} MB")
    print(f"VRAM After: {final_vram.allocated_mb:.0f} MB")
    print(f"VRAM Delta: {final_vram.allocated_mb - initial_vram.allocated_mb:+.0f} MB")
    
    # Check if truly parallel
    max_parallel_seen = max((r.max_parallel for r in results), default=0)
    was_parallel = max_parallel_seen > 1
    
    print(f"\n🔍 Parallelism Analysis:")
    print(f"   Max Parallel Requests Observed: {max_parallel_seen}")
    print(f"   Execution Mode: {'✅ TRUE PARALLEL' if was_parallel else '❌ SEQUENTIAL (queued)'}")
    
    if not was_parallel and num_parallel > 1:
        print(f"\n⚠️  ATTENTION: Requests were NOT parallel!")
        print(f"   This means the API processed them sequentially.")
        print(f"   To enable true parallelism:")
        print(f"   1. Edit the API's main.py")
        print(f"   2. Change: GPU_SEMAPHORE = asyncio.Semaphore({num_parallel})")
        print(f"   3. Restart the API")
    
    print(f"\n📋 Individual Request Results:")
    for r in results:
        status = "✅" if r.success else "❌"
        parallel_note = f" (ran with {r.max_parallel} parallel)" if r.max_parallel > 1 else " (sequential)"
        print(f"   {status} Request #{r.request_id}: {r.duration:.1f}s{parallel_note}")
    
    return results


async def run_test(num_parallel: int = 2, test_both_apis: bool = True):
    """Main test runner"""
    
    print("=" * 80)
    print(f"🧪 Parallel API Test (Semaphore > 1 required)")
    print("=" * 80)
    print(f"\nTest Configuration:")
    print(f"   Parallel requests per API: {num_parallel}")
    print(f"   VRAM monitoring interval: {MONITORING_INTERVAL}s")
    print(f"   Queue monitoring interval: {QUEUE_CHECK_INTERVAL}s")
    print(f"   Test both APIs: {test_both_apis}")
    
    # Validate videos
    for api_name, rel_path in TEST_VIDEOS.items():
        full_path = Path(__file__).parent / video_path
        if not full_path.exists():
            print(f"\n❌ Error: Test video not found: {full_path}")
            print(f"   Please ensure the video exists or update TEST_VIDEOS in the script")
            return
        print(f"   - {api_name}: {video_path}")
    
    async with aiohttp.ClientSession() as session:
        prtest_parallel_api(api_url: str, 
                           video_path: str, 
                           num_parallel: int,
                           session: aiohttp.ClientSession) -> List[TestResult]:
    """Test parallel execution on a single API"""
    
    api_name = "MMAudio" if "mmaudio" in api_url.lower() else "HunyuanVideo-Foley"
    
    print(f"\n{'='*80}")
    print(f"🔥 Testing {api_name} with {num_parallel} PARALLEL requests")
    print(f"{'='*80}")
    
    # Check initial queue configuration
    initial_queue = await get_queue_status(session, api_url)
    print(f"\n📋 Queue Configuration:")
    print(f"   Max Concurrent: {initial_queue.max_concurrent}")
    print(f"   Expected Behavior: {'✅ TRUE PARALLEL' if initial_queue.max_concurrent >= num_parallel else '⚠️  SEQUENTIAL (Semaphore too low)'}")
    
    if initial_queue.max_concurrent < num_parallel:
        print(f"\n⚠️  WARNING: API max_concurrent={initial_queue.max_concurrent} < requested parallel={num_parallel}")
        print(f"   Requests will be queued, not truly parallel!")
        print(f"   Increase GPU_SEMAPHORE in the API to asyncio.Semaphore({num_parallel})")
    
    # Get initial VRAM
    initial_vram = await get_vram_usage(session, api_url)
    print(f"\n📊 Initial VRAM: {initial_vram.allocated_mb:.0f} MB")
    
    # Shared queue snapshots (all requests will copy this)
    shared_queue_snapshots = []
    
    # Start background monitoring
    stop_event = asyncio.Event()
    
    vram_monitor = asyncio.create_task(
        monitor_vram_continuously(session, api_url, [], stop_event)
    )
    queue_monitor = asyncio.create_task(
        monitor_queue_continuously(session, api_url, shared_queue_snapshots, stop_event)
    )
    
    # Prepare all requests
    params = get_default_params(api_url)
    
    print(f"\n⚡ Launching {num_parallel} requests SIMULTANEOUSLY...")
    start_time = time.time()
    
    # Send ALL requests at the SAME time
    tasks = [
        send_request(session, api_url, video_path, params, i+1, shared_queue_snapshots)
        for i in range(num_parallel)
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    results = [r for r in results if isinstance(r, TestResult)]
    
    total_time = time.time() - start_time
    
    # Stop monitoring
    stop_event.set()
    await vram_monitor
    await queue_monitor
    
    # Get final VRAM
    final_vram = await get_vram_usage(session, api_url)
    
    # Analyze results
    print(f"\n{'='*80}")
    print(f"📊 {api_name} Results")
    print(f"{'='*80}")
    parser = argparse.ArgumentParser(description="Test parallel API inference")
    parser.add_argument("--parallel", type=int, default=2, 
                       help="Number of parallel requests per API (default: 2)")
    parser.add_argument("--mmaudio-only", action="store_true",
                       help="Only test MMAudio API")
    parser.add_argument("--hyvf-only", action="store_true",
                       help="Only test HunyuanVideo-Foley API")
    
    args = parser.parse_args()
    
    test_both = not (args.mmaudio_only or args.hyvf_only)
    
    try:
        asyncio.run(run_test(args.parallel, test_both))
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interruptedb - initial_vram.allocated_mb:+.0f} MB")
    
    # Check if truly parallel
    max_parallel_seen = max((r.max_parallel for r in results), default=0)
    was_parallel = max_parallel_seen > 1
    
    print(f"\n🔍 Parallelism Analysis:")
    print(f"   Max Parallel Requests Observed: {max_parallel_seen}")
    print(f"   Execution Mode: {'✅ TRUE PARALLEL' if was_parallel else '❌ SEQUENTIAL (queued)'}")
    
    if not was_parallel and num_parallel > 1:
        print(f"\n⚠️  ATTENTION: Requests were NOT parallel!")
        print(f"   This means the API processed them sequentially.")
        print(f"   To enable true parallelism:")
        print(f"   1. Edit the API's main.py")
        print(f"   2. Change: GPU_SEMAPHORE = asyncio.Semaphore({num_parallel})")
        print(f"   3. Restart the API")
    
    print(f"\n📋 Individual Request Results:")
    for r in results:
        status = "✅" if r.success else "❌"
        parallel_note = f" (ran with {r.max_parallel} parallel)" if r.max_parallel > 1 else " (sequential)"
        print(f"   {status} Request #{r.request_id}: {r.duration:.1f}s{parallel_note}")
    
    return results


async def run_test(num_parallel: int = 2, test_both_apis: bool = True):
    """Main test runner"""
    
    print("=" * 80)
    print(f"🧪 Parallel API Test (Semaphore > 1 required)")
    print("=" * 80)
    print(f"\nTest Configuration:")
    print(f"   Parallel requests per API: {num_parallel}")
    print(f"   VRAM monitoring interval: {MONITORING_INTERVAL}s")
    print(f"   Queue monitoring interval: {QUEUE_CHECK_INTERVAL}s")
    print(f"   Test both APIs: {test_both_apis}")
    
    # Validate videos
    for api_name, rel_path in TEST_VIDEOS.items():
        video_path = Path(__file__).parent / rel_path
        if not video_path.exists():
            print(f"\n❌ Video not found: {video_path}")
            return
    
    async with aiohttp.ClientSession() as session:
        all_results = []
        
        # Test MMAudio
        mmaudio_video = str(Path(__file__).parent / TEST_VIDEOS["mmaudio"])
        mmaudio_results = await test_parallel_api(MMAUDIO_URL, mmaudio_video, num_parallel, session)
        all_results.extend(mmaudio_results)
        
        if test_both_apis:
            # Small delay between API tests
            await asyncio.sleep(5)
            
            # Test HunyuanVideo-Foley
            hyvf_video = str(Path(__file__).parent / TEST_VIDEOS["hyvf"])
            hyvf_results = await test_parallel_api(HYVF_URL, hyvf_video, num_parallel, session)
            all_results.extend(hyvf_results)
    
    # Final summary
    print(f"\n{'='*80}")
    print("🏁 FINAL SUMMARY")
    print(f"{'='*80}")
    
    success_count = sum(1 for r in all_results if r.success)
    parallel_count = sum(1 for r in all_results if r.was_parallel)
    
    print(f"\nTotal Requests: {len(all_results)}")
    print(f"Successful: {success_count}/{len(all_results)}")
    print(f"Ran in Parallel: {parallel_count}/{len(all_results)}")
    
    if parallel_count == 0 and num_parallel > 1:
        print(f"\n⚠️  NO PARALLEL EXECUTION DETECTED!")
        print(f"   The APIs are still using Semaphore(1)")
        print(f"   Increase it to Semaphore({num_parallel}) to enable parallelism"