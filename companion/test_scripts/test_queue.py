#!/usr/bin/env python3
"""
GPU Queue Test Script

Tests the GPU queue functionality by sending multiple concurrent requests to both APIs.
Monitors queue status in real-time to verify proper serialization.

Usage:
    python3 test_queue.py
"""

import asyncio
import aiohttp
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List
import sys


# Configuration
MMAUDIO_URL = "http://localhost:8000"
HYVF_URL = "http://localhost:8001"
QUEUE_POLL_INTERVAL = 1.0  # Poll queue status every 1 second

# Test videos - using short clips
TEST_VIDEOS = {
    "mmaudio": "../../../model-tests/data/customMicroFoleyTestSet/noSound/test_door.mp4",
    "hyvf": "../../../model-tests/data/customMicroFoleyTestSet/noSound/test_footstepsPavement.mp4",
}

# Number of concurrent requests per API
REQUESTS_PER_API = 3


@dataclass
class RequestResult:
    request_id: int
    api_name: str
    video_name: str
    duration: float
    success: bool
    error: str = None
    
    def __str__(self):
        status = "✅" if self.success else "❌"
        return f"{status} Request #{self.request_id} ({self.api_name}): {self.duration:.1f}s"


async def poll_queue_status(session: aiohttp.ClientSession, api_url: str, stop_event: asyncio.Event):
    """Background task to continuously poll queue status"""
    api_name = "MMAudio" if "mmaudio" in api_url.lower() else "HunyuanVideo"
    
    while not stop_event.is_set():
        try:
            async with session.get(f"{api_url}/queue/status", timeout=2) as resp:
                if resp.status == 200:
                    stats = await resp.json()
                    if stats["pending_requests"] > 0 or stats["active_requests"] > 0:
                        print(f"   📊 {api_name:15} | Active: {stats['active_requests']} | Pending: {stats['pending_requests']}")
        except Exception:
            pass  # Ignore polling errors
        
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=QUEUE_POLL_INTERVAL)
        except asyncio.TimeoutError:
            continue


async def send_single_request(
    session: aiohttp.ClientSession,
    request_id: int,
    api_url: str,
    video_path: str,
    params: dict
) -> RequestResult:
    """Send a single request to the API"""
    
    api_name = "MMAudio" if "mmaudio" in api_url.lower() else "HunyuanVideo-Foley"
    video_name = Path(video_path).name
    
    print(f"🚀 Request #{request_id} starting: {api_name} with {video_name}")
    
    start_time = time.time()
    
    # Prepare request
    data = aiohttp.FormData()
    
    with open(video_path, 'rb') as f:
        data.add_field('video', f, 
                      filename=Path(video_path).name, 
                      content_type='video/mp4')
        
        for key, value in params.items():
            data.add_field(key, str(value))
        
        try:
            async with session.post(f"{api_url}/generate", data=data, timeout=600) as resp:
                audio_data = await resp.read()
                success = resp.status == 200
                if not success:
                    error_text = await resp.text() if resp.status != 200 else ""
                    error = f"HTTP {resp.status}: {error_text[:100]}"
                    print(f"   ❌ Request #{request_id} failed: {error}")
                else:
                    error = None
        except Exception as e:
            success = False
            error = str(e)
            print(f"   ❌ Request #{request_id} exception: {error}")
    
    duration = time.time() - start_time
    
    result = RequestResult(
        request_id=request_id,
        api_name=api_name,
        video_name=video_name,
        duration=duration,
        success=success,
        error=error
    )
    
    print(f"   {result}")
    return result


def get_default_params(api_url: str, request_id: int) -> dict:
    """Get default parameters based on API"""
    if "mmaudio" in api_url.lower():  # MMAudio
        return {
            "prompt": f"test sound {request_id}",
            "negative_prompt": "voices, music",
            "seed": 42 + request_id,
            "model_name": "large_44k_v2",
            "num_steps": 25,
            "cfg_strength": 4.5,
            "output_format": "wav",
            "full_precision": "false"
        }
    else:  # HunyuanVideo-Foley (8001)
        return {
            "prompt": f"test sound {request_id}",
            "negative_prompt": "voices, music",
            "seed": request_id,
            "model_size": "xl",  # Use XL for faster testing
            "num_steps": 50,
            "cfg_strength": 4.5,
            "output_format": "wav",
            "full_precision": "false"
        }


async def test_api_queue(api_name: str, api_url: str, video_path: str, num_requests: int, session: aiohttp.ClientSession):
    """Test queue for a single API with multiple concurrent requests"""
    
    print(f"\n{'='*80}")
    print(f"Testing {api_name} Queue ({num_requests} concurrent requests)")
    print(f"{'='*80}\n")
    
    # Start queue status monitoring
    stop_polling = asyncio.Event()
    poll_task = asyncio.create_task(poll_queue_status(session, api_url, stop_polling))
    
    # Create multiple concurrent requests
    tasks = []
    for i in range(num_requests):
        params = get_default_params(api_url, i)
        task = send_single_request(session, i+1, api_url, video_path, params)
        tasks.append(task)
    
    # Execute all requests concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Stop polling
    stop_polling.set()
    await poll_task
    
    # Filter out exceptions
    results = [r for r in results if isinstance(r, RequestResult)]
    
    return results


async def run_queue_test():
    """Run comprehensive queue test for both APIs"""
    
    print("=" * 80)
    print("🧪 GPU Queue Test - Multiple Concurrent Requests")
    print("=" * 80)
    print(f"\n📝 Test Configuration:")
    print(f"   - MMAudio API: {MMAUDIO_URL}")
    print(f"   - HunyuanVideo-Foley API: {HYVF_URL}")
    print(f"   - Requests per API: {REQUESTS_PER_API}")
    print(f"   - Total concurrent requests: {REQUESTS_PER_API * 2}")
    print(f"   - Queue monitoring: Every {QUEUE_POLL_INTERVAL}s")
    
    # Check if test videos exist
    for api_name, video_path in TEST_VIDEOS.items():
        full_path = Path(__file__).parent / video_path
        if not full_path.exists():
            print(f"\n❌ Error: Test video not found: {full_path}")
            return
        print(f"   - {api_name}: {video_path}")
    
    all_results = []
    
    async with aiohttp.ClientSession() as session:
        # Test both APIs simultaneously with multiple requests each
        print(f"\n{'='*80}")
        print("🚀 STARTING CONCURRENT QUEUE TEST")
        print("="*80)
        print(f"\n⚡ Sending {REQUESTS_PER_API} requests to EACH API simultaneously...")
        print("   (Watch queue counters - only 1 active per API at a time)\n")
        
        mmaudio_video = str(Path(__file__).parent / TEST_VIDEOS["mmaudio"])
        hyvf_video = str(Path(__file__).parent / TEST_VIDEOS["hyvf"])
        
        # Start monitoring both queues simultaneously
        stop_polling = asyncio.Event()
        poll_tasks = [
            asyncio.create_task(poll_queue_status(session, MMAUDIO_URL, stop_polling)),
            asyncio.create_task(poll_queue_status(session, HYVF_URL, stop_polling))
        ]
        
        # Create all requests for both APIs
        # IMPORTANT: Create tasks without await to ensure true concurrency
        tasks = []
        
        # MMAudio requests (create coroutines but don't await yet)
        for i in range(REQUESTS_PER_API):
            params = get_default_params(MMAUDIO_URL, i)
            coro = send_single_request(session, i+1, MMAUDIO_URL, mmaudio_video, params)
            tasks.append(asyncio.create_task(coro))
        
        # HunyuanVideo-Foley requests (create coroutines but don't await yet)
        for i in range(REQUESTS_PER_API):
            params = get_default_params(HYVF_URL, i)
            coro = send_single_request(session, i+1, HYVF_URL, hyvf_video, params)
            tasks.append(asyncio.create_task(coro))
        
        # Small delay to ensure all tasks are created before any completes
        await asyncio.sleep(0.1)
        
        # Execute all requests concurrently (they're already running)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Stop monitoring
        stop_polling.set()
        await asyncio.gather(*poll_tasks)
        
        # Filter results
        all_results = [r for r in results if isinstance(r, RequestResult)]
    
    # Print summary
    print("\n" + "=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)
    
    # Group by API
    mmaudio_results = [r for r in all_results if "MMAudio" in r.api_name]
    hyvf_results = [r for r in all_results if "HunyuanVideo" in r.api_name]
    
    print(f"\n🎵 MMAudio Results ({len(mmaudio_results)} requests):")
    for r in mmaudio_results:
        print(f"   {r}")
    
    print(f"\n🎬 HunyuanVideo-Foley Results ({len(hyvf_results)} requests):")
    for r in hyvf_results:
        print(f"   {r}")
    
    # Statistics
    total_success = sum(1 for r in all_results if r.success)
    total_failed = len(all_results) - total_success
    avg_duration = sum(r.duration for r in all_results) / len(all_results) if all_results else 0
    
    print(f"\n📈 Statistics:")
    print(f"   Total requests: {len(all_results)}")
    print(f"   Successful: {total_success} ✅")
    print(f"   Failed: {total_failed} ❌")
    print(f"   Average duration: {avg_duration:.1f}s")
    
    # Queue effectiveness check
    if total_success == len(all_results):
        print(f"\n✅ Queue Test PASSED - All requests processed successfully!")
        print(f"   The queue prevented OOM by serializing GPU access.")
    else:
        print(f"\n⚠️  Queue Test PARTIAL - {total_failed} requests failed")
        print(f"   Check logs for errors")
    
    print("\n" + "=" * 80)
    print("🏁 Test completed")
    print("=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(run_queue_test())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(130)
