#!/usr/bin/env python3
"""
Video Retrieval Testing & Baseline Evaluation

Tests X-CLIP based sound retrieval with various test videos.
Generates results for manual evaluation and baseline metrics.

Usage:
    python test_video_retrieval.py                    # Test all videos with 8 frames (default)
    python test_video_retrieval.py --frames 16        # Test with 16 frames
    python test_video_retrieval.py --video test_car   # Test single video
"""

import os
import sys
import argparse
import json
from pathlib import Path
from typing import List, Dict, Any
import csv
from datetime import datetime

import requests

# Configuration
API_URL = os.getenv("SOUND_SEARCH_API_URL", "http://localhost:8002")
TEST_VIDEO_DIR = Path(__file__).parent.parent.parent.parent / "model-tests/data/customMicroFoleyTestSet/noSound"
OUTPUT_DIR = Path(__file__).parent.parent / "test_results"

# Test videos with expected sound categories
# Each entry contains:
#   - expected_keywords: List of keywords that should appear in relevant results
#                       Used for automatic Precision@K calculation via keyword matching
#   - description: Human-readable ground truth label (what the video shows)
#                 For documentation only, not used in evaluation
#   - prompt: Text prompt to guide retrieval (used when --use-prompts flag is set)
TEST_VIDEOS = {
    'test_carPassing.mp4': {
        'expected_keywords': ['car', 'vehicle', 'traffic', 'road', 'engine', 'motor'],
        'description': 'Car driving by',
        'prompt': 'car driving by'
    },
    'test_dogBarking.mp4': {
        'expected_keywords': ['dog', 'bark', 'animal', 'pet'],
        'description': 'Dog barking',
        'prompt': 'dog barking'
    },
    'test_door.mp4': {
        'expected_keywords': ['door', 'open', 'close', 'creak', 'handle'],
        'description': 'Door opening/closing',
        'prompt': 'door opening and closing'
    },
    'test_footstepsGravel.mp4': {
        'expected_keywords': ['footsteps', 'gravel', 'walking', 'steps', 'stones'],
        'description': 'Person walking on gravel',
        'prompt': 'footsteps on gravel'
    },
    'test_footstepsPavement.mp4': {
        'expected_keywords': ['footsteps', 'pavement', 'walking', 'steps', 'concrete'],
        'description': 'Person walking on pavement',
        'prompt': 'footsteps on pavement'
    },
    'test_rainWindow.mp4': {
        'expected_keywords': ['rain', 'water', 'window', 'drops', 'weather'],
        'description': 'Rain drops on window',
        'prompt': 'rain'
    },
    'test_snowStepsClothing.mp4': {
        'expected_keywords': ['snow', 'footsteps', 'walking', 'crunch', 'clothing'],
        'description': 'Walking in snow with clothing rustle',
        'prompt': 'footsteps in snow'
    },
    'test_toast.mp4': {
        'expected_keywords': ['toast', 'glasses', 'cling', 'laughter', 'women'],
        'description': 'Toaster popping',
        'prompt': 'people laughing and clinking glasses'
    }
}


def check_api_health() -> bool:
    """Check if Sound Search API is available"""
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        response.raise_for_status()
        health = response.json()
        print(f"✓ API healthy: {health['available_sounds']} sounds, {health['sounds_with_embeddings']} with embeddings")
        return True
    except Exception as e:
        print(f"❌ API not available: {e}")
        return False


def search_video(video_path: Path, limit: int = 10, threshold: float = 0.0, num_frames: int = 8, 
                text_prompt: str = None, text_weight: float = 0.3) -> List[Dict[str, Any]]:
    """
    Search sounds by video using X-CLIP video encoder
    
    Process:
    1. Upload video file to sound-search-API
    2. API extracts num_frames uniformly sampled frames from video
    3. X-CLIP encodes frames → video embedding
    4. If text_prompt provided: fuses video + text embeddings
    5. PostgreSQL vector search finds nearest text embeddings (cosine similarity)
    6. Returns Top-K BBC sounds with similarity scores
    
    Args:
        video_path: Path to test video file
        limit: Max results to return (Top-K)
        threshold: Min similarity threshold (0-1), filters low-confidence results
        num_frames: Number of frames to extract from video
                   More frames = better temporal coverage but slower encoding
                   Default 8 frames matches X-CLIP training
        text_prompt: Optional text prompt to guide retrieval (e.g., "car passing")
                    Enables hybrid video+text search
        text_weight: Weight for text prompt in hybrid search (default: 0.3)
                    Final = (1-text_weight)*video + text_weight*text
    
    Returns:
        List of sound dicts with: id, description, category, similarity, file_path
        Sorted by descending similarity (most similar first)
    """
    try:
        # Open video file in binary mode
        with open(video_path, 'rb') as f:
            # Build request data
            data = {
                'limit': limit,
                'threshold': threshold,
                'num_frames': num_frames
            }
            
            # Add text prompt if provided
            if text_prompt:
                data['text'] = text_prompt
                data['text_weight'] = text_weight
            
            # POST request with multipart/form-data
            response = requests.post(
                f"{API_URL}/search/sounds",
                files={'video': f},  # Video file upload
                data=data,
                timeout=60  # X-CLIP encoding can take 5-30 seconds depending on video length
            )
        response.raise_for_status()
        return response.json()['results']
    except Exception as e:
        print(f"❌ Search failed for {video_path.name}: {e}")
        return []


def calculate_precision_at_k(results: List[Dict], expected_keywords: List[str], k: int = 5) -> float:
    """
    Calculate Precision@K - fraction of top-K results that are relevant
    
    Precision@K = (# relevant results in top-K) / K
    
    Example: If top-5 results contain 3 sounds with "footsteps", Precision@5 = 3/5 = 0.6
    
    Relevance Criteria (automatic):
    A result is considered relevant if ANY expected keyword appears in:
    - Sound description (e.g., "Footsteps on gravel")
    - Sound category (e.g., "Walking & Footsteps")
    Case-insensitive substring matching
    
    Args:
        results: List of search results from API (sorted by similarity)
        expected_keywords: List of keywords that indicate relevant sounds
                          Example: ['car', 'vehicle', 'engine'] for car video
        k: Number of top results to evaluate (typically 5 or 10)
    
    Returns:
        Precision@K score between 0.0 (no relevant) and 1.0 (all relevant)
    """
    if not results or not expected_keywords:
        return 0.0
    
    # Take only top-K results
    top_k = results[:k]
    relevant_count = 0
    
    # Check each result for relevance
    for result in top_k:
        description = result['description'].lower()
        category = (result.get('category') or '').lower()
        combined_text = f"{description} {category}"
        
        # Result is relevant if ANY expected keyword appears
        # Example: "footsteps" matches "Footsteps on gravel"
        if any(keyword.lower() in combined_text for keyword in expected_keywords):
            relevant_count += 1
    
    return relevant_count / k


def calculate_mrr(results: List[Dict], expected_keywords: List[str]) -> float:
    """
    Calculate Mean Reciprocal Rank - measures rank position of first relevant result
    
    MRR = 1 / (rank of first relevant result)
    
    Examples:
    - First result relevant → MRR = 1/1 = 1.0 (perfect)
    - Second result relevant → MRR = 1/2 = 0.5
    - Third result relevant → MRR = 1/3 = 0.333
    - No relevant results → MRR = 0.0
    
    MRR rewards systems that put relevant results at the top.
    Higher MRR = better ranking quality
    
    Args:
        results: List of search results (sorted by similarity descending)
        expected_keywords: Keywords indicating relevant sounds
    
    Returns:
        MRR score between 0.0 (no relevant) and 1.0 (top result relevant)
    """
    # Iterate through results with 1-based ranking
    for rank, result in enumerate(results, 1):
        description = result['description'].lower()
        category = (result.get('category') or '').lower()
        combined_text = f"{description} {category}"
        
        # Check if this result is relevant
        if any(keyword.lower() in combined_text for keyword in expected_keywords):
            # Found first relevant result - return reciprocal of its rank
            return 1.0 / rank
    
    # No relevant results found in entire list
    return 0.0


def save_results_csv(all_results: List[Dict], output_path: Path):
    """
    Save results to CSV for manual review and annotation
    
    CSV Format:
    - One row per retrieved sound (80 rows for 8 videos × 10 results)
    - Auto Relevant: Automatic relevance (keyword matching)
    - Manual Relevant: Empty column for human annotation (YES/NO)
    
    Workflow:
    1. Script generates CSV with automatic relevance
    2. Human reviewer opens CSV in Excel/LibreOffice
    3. Reviewer fills "Manual Relevant" column (YES/NO) based on actual relevance
    4. Compare automatic vs manual Precision@5 to validate keyword-based evaluation
    
    Args:
        all_results: List of test results (one dict per video)
        output_path: Where to save CSV file
    """
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # CSV Header
        writer.writerow([
            'Video',              # Test video filename
            'Rank',               # Result rank (1-10)
            'Sound ID',           # BBC Sound Archive ID
            'Description',        # Sound description
            'Category',           # Sound category
            'Similarity',         # X-CLIP cosine similarity (0-1)
            'Expected Keywords',  # Ground truth keywords for this video
            'Auto Relevant',      # Automatic relevance (YES/NO)
            'Manual Relevant'     # For human annotation (leave empty)
        ])
        
        # Write results for each video
        for video_result in all_results:
            video_name = video_result['video']
            expected = ', '.join(video_result['expected_keywords'])
            
            # Write each retrieved sound as a row
            for rank, result in enumerate(video_result['results'], 1):
                description = result['description'].lower()
                category = (result.get('category') or '').lower()
                combined_text = f"{description} {category}"
                
                # Automatic relevance via keyword matching
                # YES if any expected keyword appears in description or category
                auto_relevant = 'YES' if any(kw.lower() in combined_text for kw in video_result['expected_keywords']) else 'NO'
                
                writer.writerow([
                    video_name,
                    rank,
                    result['id'],
                    result['description'],  # Original case for readability
                    result.get('category', ''),
                    f"{result.get('similarity', 0):.4f}",
                    expected,
                    auto_relevant,
                    ''  # Empty - human fills this during manual review
                ])


def save_results_json(all_results: List[Dict], output_path: Path):
    """Save detailed results to JSON"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)


def print_results(video_name: str, results: List[Dict], expected_keywords: List[str], num_frames: int):
    """
    Pretty print search results to console with relevance markers
    
    Format:
    ✓ 1. [0.823] Footsteps on gravel    ← Relevant (contains expected keyword)
        Category: Walking & Footsteps
      2. [0.654] Car engine starting     ← Not relevant
        Category: Vehicles
    
    Shows top-10 results with:
    - ✓ marker for automatically relevant results (keyword match)
    - Rank number (1-10)
    - Similarity score in brackets
    - Description and category
    
    Args:
        video_name: Name of test video
        results: List of retrieved sounds
        expected_keywords: Ground truth keywords for relevance checking
        num_frames: Number of frames used (for documentation)
    """
    print(f"\n{'='*80}")
    print(f"Video: {video_name} (frames: {num_frames})")
    print(f"Expected: {', '.join(expected_keywords)}")
    print(f"{'='*80}")
    
    if not results:
        print("❌ No results found")
        return
    
    # Display top-10 results
    for rank, result in enumerate(results[:10], 1):
        description = result['description']
        category = result.get('category') or 'N/A'
        similarity = result.get('similarity', 0)
        
        # Check if this result matches expected keywords (automatic relevance)
        combined = f"{description.lower()} {(category or '').lower()}"
        is_relevant = any(kw.lower() in combined for kw in expected_keywords)
        marker = "✓" if is_relevant else " "  # Checkmark for relevant results
        
        # Format: [marker] rank. [similarity] description
        print(f"{marker} {rank:2d}. [{similarity:.3f}] {description}")
        print(f"      Category: {category}")
    
    # Calculate and display evaluation metrics
    precision_5 = calculate_precision_at_k(results, expected_keywords, k=5)
    mrr = calculate_mrr(results, expected_keywords)
    
    print(f"\n📊 Metrics:")
    print(f"   Precision@5: {precision_5:.2%}")  # Percentage of top-5 that are relevant
    print(f"   MRR: {mrr:.3f}")  # Reciprocal rank of first relevant result


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Test video-based sound retrieval with optional text prompts'
    )
    parser.add_argument(
        '--video',
        type=str,
        help='Test single video (filename without path)'
    )
    parser.add_argument(
        '--frames',
        type=int,
        choices=[8, 16],
        default=8,
        help='Number of frames to extract from video (default: 8)'
    )
    parser.add_argument(
        '--use-prompts',
        action='store_true',
        help='Use text prompts from TEST_VIDEOS to guide retrieval (hybrid search)'
    )
    parser.add_argument(
        '--text-weight',
        type=float,
        default=0.3,
        help='Weight for text prompt in hybrid search (default: 0.3 = 30%% text, 70%% video)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='Number of results to retrieve (default: 10)'
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=0.0,
        help='Minimum similarity threshold (default: 0.0)'
    )
    return parser.parse_args()


def main():
    """
    Main testing function - orchestrates the complete evaluation workflow
    
    Workflow:
    1. Parse command line arguments (--frames, --video, etc.)
    2. Check API availability and database status
    3. For each test video:
       a. Upload video to sound-search-API
       b. Retrieve top-10 most similar BBC sounds
       c. Calculate automatic relevance metrics (Precision@5, MRR)
       d. Display results to console
    4. Save all results to CSV (for manual review) and JSON (detailed data)
    5. Display summary statistics (average Precision@5, average MRR)
    
    Output Files:
    - CSV: retrieval_test_{frames}frames_{timestamp}.csv
          For manual annotation in Excel/LibreOffice
    - JSON: retrieval_test_{frames}frames_{timestamp}.json
           Complete structured data for analysis
    
    Returns:
        0 on success, 1 on error
    """
    args = parse_args()
    
    print("="*80)
    print("BBC Sound Archive - Video Retrieval Testing")
    print(f"Frames per video: {args.frames}")
    if args.use_prompts:
        print(f"Mode: HYBRID (video + text prompts, text_weight={args.text_weight})")
    else:
        print("Mode: VIDEO-ONLY")
    print("="*80)
    print()
    
    # Step 1: Check API availability
    if not check_api_health():
        return 1
    
    # Step 2: Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Step 3: Select videos to test
    if args.video:
        # Single video mode (for quick testing)
        if args.video not in TEST_VIDEOS:
            print(f"❌ Unknown video: {args.video}")
            print(f"Available: {', '.join(TEST_VIDEOS.keys())}")
            return 1
        videos_to_test = {args.video: TEST_VIDEOS[args.video]}
    else:
        # Test all videos (default - full evaluation)
        videos_to_test = TEST_VIDEOS
    
    # Step 4: Test each video and accumulate results
    all_results = []
    total_precision_5 = 0.0  # Sum of Precision@5 for averaging
    total_mrr = 0.0           # Sum of MRR for averaging
    
    for video_name, video_info in videos_to_test.items():
        video_path = TEST_VIDEO_DIR / video_name
        
        if not video_path.exists():
            print(f"❌ Video not found: {video_path}")
            continue
        
        print(f"\n🎥 Testing: {video_name}")
        print(f"   {video_info['description']}")
        if args.use_prompts:
            print(f"   📝 Prompt: \"{video_info['prompt']}\"")
        
        # Search
        results = search_video(
            video_path,
            limit=args.limit,
            threshold=args.threshold,
            num_frames=args.frames,
            text_prompt=video_info['prompt'] if args.use_prompts else None,
            text_weight=args.text_weight
        )
        
        if results:
            # Print results
            print_results(video_name, results, video_info['expected_keywords'], args.frames)
            
            # Calculate metrics
            precision_5 = calculate_precision_at_k(results, video_info['expected_keywords'], k=5)
            mrr = calculate_mrr(results, video_info['expected_keywords'])
            
            total_precision_5 += precision_5
            total_mrr += mrr
            
            # Store results
            all_results.append({
                'video': video_name,
                'description': video_info['description'],
                'expected_keywords': video_info['expected_keywords'],
                'num_frames': args.frames,
                'results': results,
                'precision_at_5': precision_5,
                'mrr': mrr
            })
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode_suffix = f"hybrid_tw{args.text_weight:.1f}" if args.use_prompts else "video"
    csv_path = OUTPUT_DIR / f"retrieval_test_{args.frames}frames_{mode_suffix}_{timestamp}.csv"
    json_path = OUTPUT_DIR / f"retrieval_test_{args.frames}frames_{mode_suffix}_{timestamp}.json"
    
    save_results_csv(all_results, csv_path)
    save_results_json(all_results, json_path)
    
    # Summary
    num_videos = len(all_results)
    avg_precision_5 = total_precision_5 / num_videos if num_videos > 0 else 0
    avg_mrr = total_mrr / num_videos if num_videos > 0 else 0
    
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Videos tested: {num_videos}")
    print(f"Frames per video: {args.frames}")
    if args.use_prompts:
        print(f"Mode: Hybrid (text_weight={args.text_weight})")
    else:
        print("Mode: Video-only")
    print(f"Average Precision@5: {avg_precision_5:.2%}")
    print(f"Average MRR: {avg_mrr:.3f}")
    print()
    print(f"Results saved:")
    print(f"  CSV:  {csv_path}")
    print(f"  JSON: {json_path}")
    print()
    print("Next steps:")
    print("1. Open CSV file for manual review")
    print("2. Mark 'Manual Relevant' column (YES/NO) for each result")
    print("3. Calculate manual Precision@5 for comparison")
    print("="*80)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
