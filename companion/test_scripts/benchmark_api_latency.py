#!/usr/bin/env python3
"""Benchmark CLI-like API calls via localhost vs Cloudflare endpoints.

This script measures and compares the latency of API calls to different services
(MMAudio, HunyuanVideo) through both local and Cloudflare tunnel endpoints.

Usage:
    cd protools-aax/companion
    python test_scripts/benchmark_api_latency.py --service mmaudio --video path/to/test.mp4 --runs 3
    python test_scripts/benchmark_api_latency.py --service hunyuan --video path/to/test.mp4 --runs 3
    python test_scripts/benchmark_api_latency.py --service hunyuan_xl --video path/to/test.mp4 --runs 3
    python test_scripts/benchmark_api_latency.py --service mmaudio --video path/to/test.mp4 --runs 5 --skip-local
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

sys.path.append(str(Path(__file__).resolve().parents[1]))  # companion/
from api.config import get_config, get_cf_headers, get_api_url, use_cloudflared  # noqa: E402
from video.ffmpeg import get_video_duration as ffmpeg_get_duration  # noqa: E402

SERVICE_PAYLOADS = {
    "mmaudio": {
        "data": {
            "prompt": "benchmark prompt",
            "negative_prompt": "voices, music",
            "seed": 42,
            "model_name": "large_44k_v2",
            "num_steps": 25,
            "cfg_strength": 4.5,
            "output_format": "wav",
            "full_precision": False,
            # duration will be set dynamically from video
        }
    },
    "hunyuan": {
        "data": {
            "prompt": "benchmark prompt",
            "negative_prompt": "voices, music",
            "seed": 42,
            "model_size": "xxl",
            "num_steps": 50,
            "cfg_strength": 4.5,
            "output_format": "wav",
            "full_precision": False,
            # duration will be set dynamically from video
        }
    },
    "hunyuan_xl": {
        "data": {
            "prompt": "benchmark prompt",
            "negative_prompt": "voices, music",
            "seed": 42,
            "model_size": "xl",
            "num_steps": 50,
            "cfg_strength": 4.5,
            "output_format": "wav",
            "full_precision": False,
            # duration will be set dynamically from video
        }
    },
}


@dataclass
class Result:
    """Represents a single API request result with timing and transfer metrics."""
    endpoint: str
    elapsed: float
    status: int
    upload_bytes: int
    download_bytes: int
    error: Optional[str] = None
    upload_time: float = 0.0
    processing_time: float = 0.0
    download_time: float = 0.0

    @property
    def success(self) -> bool:
        """Returns True if the request was successful."""
        return self.error is None and 200 <= self.status < 300

    @property
    def upload_speed_mbps(self) -> float:
        """Calculate upload speed in Mbps."""
        if self.upload_time > 0:
            return (self.upload_bytes * 8) / (self.upload_time * 1e6)
        return 0.0

    @property
    def download_speed_mbps(self) -> float:
        """Calculate download speed in Mbps."""
        if self.download_time > 0:
            return (self.download_bytes * 8) / (self.download_time * 1e6)
        return 0.0


def get_video_duration(video_path: Path) -> Optional[float]:
    """Extract duration from video file in seconds using FFmpeg.
    
    Uses the project's existing FFmpeg integration (video.ffmpeg.get_video_duration).
    
    Args:
        video_path: Path to the video file
        
    Returns:
        Duration in seconds, or None if it cannot be determined
    """
    result = ffmpeg_get_duration(str(video_path))
    if result['success']:
        return result['duration']
    else:
        print(f"Warning: Could not get video duration: {result['error']}", file=sys.stderr)
        return None


def build_form_data(data: Dict[str, Any]) -> Dict[str, str]:
    """Convert payload dictionary to form data with proper type serialization."""
    form = {}
    for key, value in data.items():
        if isinstance(value, bool):
            form[key] = json.dumps(value)
        elif isinstance(value, (int, float)):
            form[key] = str(value)
        elif isinstance(value, str):
            form[key] = value
        else:
            form[key] = json.dumps(value)
    return form


def send_request(service: str, url: str, video_path: Path, headers: Dict[str, str]) -> Result:
    """Send a single benchmark request and measure timing details.
    
    Args:
        service: Service name (mmaudio or hunyuan)
        url: Base URL of the API endpoint
        video_path: Path to the video file to upload
        headers: HTTP headers for the request
        
    Returns:
        Result object with timing and transfer metrics
    """
    payload = SERVICE_PAYLOADS[service]["data"].copy()
    
    # Set duration from video metadata
    duration = get_video_duration(video_path)
    if duration is None:
        return Result(
            endpoint=url,
            elapsed=0.0,
            status=-1,
            upload_bytes=0,
            download_bytes=0,
            error="Failed to determine video duration"
        )
    payload["duration"] = duration
    
    try:
        video_bytes = video_path.read_bytes()
    except (OSError, IOError) as exc:
        return Result(
            endpoint=url,
            elapsed=0.0,
            status=-1,
            upload_bytes=0,
            download_bytes=0,
            error=f"Failed to read video file: {exc}"
        )
    
    files = {"video": (video_path.name, video_bytes, "video/mp4")}
    upload_bytes = len(video_bytes)

    start_time = time.perf_counter()
    try:
        response = requests.post(
            f"{url}/generate",
            headers=headers,
            data=build_form_data(payload),
            files=files,
            timeout=900,
            stream=False
        )
        elapsed = time.perf_counter() - start_time
        download_bytes = len(response.content)
        
        response.raise_for_status()
        
        return Result(
            endpoint=url,
            elapsed=elapsed,
            status=response.status_code,
            upload_bytes=upload_bytes,
            download_bytes=download_bytes,
            error=None
        )
    except requests.Timeout:
        elapsed = time.perf_counter() - start_time
        return Result(
            endpoint=url,
            elapsed=elapsed,
            status=-1,
            upload_bytes=upload_bytes,
            download_bytes=0,
            error="Request timeout (900s)"
        )
    except requests.RequestException as exc:
        elapsed = time.perf_counter() - start_time
        status = getattr(exc.response, "status_code", -1) if hasattr(exc, "response") else -1
        download_bytes = len(getattr(exc.response, "content", b"")) if hasattr(exc, "response") else 0
        error_msg = f"{type(exc).__name__}: {str(exc)}"
        
        return Result(
            endpoint=url,
            elapsed=elapsed,
            status=status,
            upload_bytes=upload_bytes,
            download_bytes=download_bytes,
            error=error_msg
        )


def summarize(results: List[Result]) -> None:
    """Print a comprehensive summary of benchmark results grouped by endpoint."""
    if not results:
        print("No results to summarize.")
        return

    grouped: Dict[str, List[Result]] = {}
    for result in results:
        grouped.setdefault(result.endpoint, []).append(result)

    print("\n" + "=" * 80)
    print("BENCHMARK RESULTS")
    print("=" * 80)

    for endpoint, rows in grouped.items():
        successes = [r for r in rows if r.success]
        success_times = [r.elapsed for r in successes]
        
        print(f"\nEndpoint: {endpoint}")
        print(f"  Total Runs: {len(rows)}")
        print(f"  Successes: {len(successes)} ({len(successes)/len(rows)*100:.1f}%)")
        print(f"  Failures: {len(rows) - len(successes)}")
        
        if success_times:
            avg_time = statistics.mean(success_times)
            median_time = statistics.median(success_times)
            min_time = min(success_times)
            max_time = max(success_times)
            stdev_time = statistics.stdev(success_times) if len(success_times) > 1 else 0.0
            
            print(f"\n  Timing Statistics (successful requests):")
            print(f"    Average:   {avg_time:7.2f}s")
            print(f"    Median:    {median_time:7.2f}s")
            print(f"    Min:       {min_time:7.2f}s")
            print(f"    Max:       {max_time:7.2f}s")
            print(f"    Std Dev:   {stdev_time:7.2f}s")
            
            # Transfer statistics
            avg_upload_mb = statistics.mean([r.upload_bytes / 1e6 for r in successes])
            avg_download_mb = statistics.mean([r.download_bytes / 1e6 for r in successes])
            
            print(f"\n  Transfer Statistics (successful requests):")
            print(f"    Avg Upload:   {avg_upload_mb:7.2f} MB")
            print(f"    Avg Download: {avg_download_mb:7.2f} MB")
        
        print(f"\n  Individual Results:")
        for i, r in enumerate(rows, 1):
            if r.success:
                status_str = f"✓ HTTP {r.status}"
            else:
                status_str = f"✗ {r.error or f'HTTP {r.status}'}"
            
            print(
                f"    Run {i}: {r.elapsed:6.2f}s | "
                f"↑ {r.upload_bytes / 1e6:6.2f} MB | "
                f"↓ {r.download_bytes / 1e6:6.2f} MB | "
                f"{status_str}"
            )
    
    print("\n" + "=" * 80)


def get_endpoints(service: str, skip_local: bool = False, skip_cloudflare: bool = False) -> List[Tuple[str, Dict[str, str], str]]:
    """Get API endpoint configurations for benchmarking.
    
    Args:
        service: Service name (mmaudio, hunyuan, or hunyuan_xl)
        skip_local: If True, exclude local endpoint
        skip_cloudflare: If True, exclude Cloudflare endpoint
        
    Returns:
        List of tuples containing (url, headers, label)
    """
    from api.config import reload_config
    
    # Map service names to config keys
    service_map = {
        "mmaudio": "mmaudio",
        "hunyuan": "hunyuan",
        "hunyuan_xl": "hunyuan",  # Both hunyuan variants use same endpoint
    }
    
    config_service = service_map.get(service, service)
    endpoints: List[Tuple[str, Dict[str, str], str]] = []

    # Local endpoint
    if not skip_local:
        try:
            cfg = get_config()
            local_url = cfg["services"][config_service]["api_url_direct"]
            headers_local = {}
            endpoints.append((local_url, headers_local, "Local"))
        except Exception as exc:
            print(f"Warning: Could not configure local endpoint: {exc}", file=sys.stderr)

    # Cloudflare endpoint
    if not skip_cloudflare:
        try:
            cfg = get_config()
            cloud_url = cfg["services"][config_service]["api_url_cloudflared"]
            
            # Get Cloudflare Access headers if configured
            headers_cf = {}
            client_id = cfg.get("cf_access_client_id", "")
            client_secret = cfg.get("cf_access_client_secret", "")
            if client_id and client_secret:
                headers_cf = {
                    "CF-Access-Client-Id": client_id,
                    "CF-Access-Client-Secret": client_secret,
                }
            
            if not cloud_url:
                print(f"Warning: No Cloudflare URL configured for {config_service}", file=sys.stderr)
            else:
                endpoints.append((cloud_url, headers_cf, "Cloudflare"))
        except Exception as exc:
            print(f"Warning: Could not configure Cloudflare endpoint: {exc}", file=sys.stderr)
    
    if not endpoints:
        raise ValueError("No valid endpoints configured")

    return endpoints


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark localhost vs Cloudflare API latency",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare local and Cloudflare with 3 runs each
  python benchmark_api_latency.py --service mmaudio --video test.mp4 --runs 3
  
  # Only test Cloudflare endpoint
  python benchmark_api_latency.py --service hunyuan --video test.mp4 --runs 5 --skip-local
  
  # Only test local endpoint
  python benchmark_api_latency.py --service mmaudio --video test.mp4 --skip-cloudflare
        """
    )
    parser.add_argument(
        "--service",
        choices=list(SERVICE_PAYLOADS.keys()),
        required=True,
        help="API service to benchmark"
    )
    parser.add_argument(
        "--video",
        type=Path,
        required=True,
        help="Path to test video file"
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of benchmark runs per endpoint (default: 3)"
    )
    parser.add_argument(
        "--skip-local",
        action="store_true",
        help="Skip testing local endpoint"
    )
    parser.add_argument(
        "--skip-cloudflare",
        action="store_true",
        help="Skip testing Cloudflare endpoint"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()

    # Validation
    if not args.video.exists():
        print(f"Error: Video file not found: {args.video}", file=sys.stderr)
        return 1
    
    if not args.video.is_file():
        print(f"Error: Path is not a file: {args.video}", file=sys.stderr)
        return 1
    
    if args.runs < 1:
        print("Error: --runs must be at least 1", file=sys.stderr)
        return 1
    
    if args.skip_local and args.skip_cloudflare:
        print("Error: Cannot skip both local and Cloudflare endpoints", file=sys.stderr)
        return 1

    # Get endpoints
    try:
        endpoints = get_endpoints(args.service, args.skip_local, args.skip_cloudflare)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Display configuration
    print(f"Benchmarking {args.service} API")
    print(f"Video: {args.video} ({args.video.stat().st_size / 1e6:.2f} MB)")
    print(f"Runs per endpoint: {args.runs}")
    print(f"Endpoints to test: {len(endpoints)}")
    for url, _, label in endpoints:
        print(f"  - {label}: {url}")
    print("\nStarting benchmark...\n")

    # Run benchmarks
    results: List[Result] = []
    total_requests = len(endpoints) * args.runs
    request_num = 0
    
    for url, headers, label in endpoints:
        print(f"Testing {label} endpoint ({url})...")
        for run in range(1, args.runs + 1):
            request_num += 1
            # Always show progress for long-running requests
            print(f"  Run {run}/{args.runs} (overall {request_num}/{total_requests})...", end=" ", flush=True)
            
            result = send_request(args.service, url, args.video, headers)
            results.append(result)
            
            if result.success:
                print(f"✓ {result.elapsed:.2f}s")
            else:
                print(f"✗ {result.error}")
        print()

    # Display results
    summarize(results)
    
    # Return non-zero if any request failed
    failures = sum(1 for r in results if not r.success)
    if failures > 0:
        print(f"\n⚠ {failures}/{len(results)} requests failed", file=sys.stderr)
        return 1
    
    print(f"\n✓ All {len(results)} requests succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
