#!/usr/bin/env python3
"""
BBC Sound Search CLI Tool

Search the BBC Sound Archive using video or text queries.
Results are powered by X-CLIP embeddings with category-enhanced retrieval.

Commands:
    search-video    Search using a video file (movement, action)
    search-text     Search using text description  
    info           Show details for a specific sound
    download       Download sound file(s) to /tmp/

Examples:
    python sound_search.py search-video /path/to/rain.mp4
    python sound_search.py search-text "footsteps on pavement"
    python sound_search.py info 5362
    python sound_search.py download 5362 1234 5678 --output /tmp/sounds/
"""

import argparse
import json
import os
import sys
import tempfile
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.config import get_cf_headers, get_api_url


# Default API endpoint: taken from the shared config.json (localhost:8002 unless configured otherwise)
DEFAULT_API_URL = get_api_url("sound_search") or "http://localhost:8002"


class SoundSearchAPI:
    """HTTP client for sound-search-API."""
    
    def __init__(self, base_url: str = DEFAULT_API_URL):
        self.base_url = base_url.rstrip('/')
        self.headers = get_cf_headers()  # Load Cloudflare Access headers if configured
        
    def search_sounds(
        self, 
        video_path: Optional[str] = None,
        text_query: Optional[str] = None,
        limit: int = 5,
        text_weight: float = 0.6,
        num_frames: int = 16
    ) -> Dict[str, Any]:
        """
        Search for sounds using video and/or text.
        
        Args:
            video_path: Path to video file
            text_query: Text description
            limit: Number of results (default: 5)
            text_weight: Weight for text vs video (0-1, default: 0.6)
            num_frames: Number of frames to extract (default: 16)
            
        Returns:
            API response dict with 'results' list
        """
        url = f"{self.base_url}/search/sounds"
        
        files = {}
        data = {
            'limit': limit,
            'text_weight': text_weight,
            'num_frames': num_frames
        }
        
        if video_path:
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")
            files['video'] = open(video_path, 'rb')
            
        if text_query:
            data['text'] = text_query
            
        if not video_path and not text_query:
            raise ValueError("Must provide either video_path or text_query")
            
        try:
            response = requests.post(url, files=files, data=data, headers=self.headers)
            response.raise_for_status()
            return response.json()
        finally:
            # Close file if opened
            if 'video' in files:
                files['video'].close()
                
    def get_sound_info(self, sound_id: int) -> Dict[str, Any]:
        """
        Get detailed information about a specific sound.
        
        Args:
            sound_id: BBC sound ID
            
        Returns:
            Sound metadata dict
        """
        url = f"{self.base_url}/sounds/{sound_id}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
        
    def download_sound(self, sound_id: int, output_path: str) -> str:
        """
        Download sound file to specified path.
        
        Args:
            sound_id: BBC sound ID
            output_path: Directory or file path to save to
            
        Returns:
            Full path to downloaded file
        """
        url = f"{self.base_url}/sounds/{sound_id}/download"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        
        # Get filename from Content-Disposition header
        content_disp = response.headers.get('Content-Disposition', '')
        if 'filename=' in content_disp:
            filename = content_disp.split('filename=')[-1].strip('"')
        else:
            # Fallback: get from sound info
            info = self.get_sound_info(sound_id)
            filename = os.path.basename(info['file_path'])
            
        # Determine output path
        if os.path.isdir(output_path):
            output_file = os.path.join(output_path, filename)
        else:
            output_file = output_path
            
        # Write file
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'wb') as f:
            f.write(response.content)
            
        return output_file


def format_result(result: Dict[str, Any], rank: int) -> str:
    """Format a search result for display."""
    lines = [
        f"[{rank}] ID: {result['id']} | Similarity: {result['similarity']:.3f}",
        f"    Category: {result['category']}",
        f"    Description: {result['description']}",
        f"    File: {os.path.basename(result['file_path'])}",
    ]
    return '\n'.join(lines)


def cmd_search_video(args):
    """Handle search-video command."""
    api = SoundSearchAPI(args.api_url)
    
    print(f"🎬 Searching with video: {args.video}")
    if args.text:
        print(f"📝 Additional text query: {args.text}")
    print(f"🔍 Retrieving top {args.limit} results...\n")
    
    try:
        response = api.search_sounds(
            video_path=args.video,
            text_query=args.text,
            limit=args.limit,
            text_weight=args.text_weight,
            num_frames=args.frames
        )
        
        results = response['results']
        
        if not results:
            print("❌ No results found")
            return
            
        print(f"✅ Found {len(results)} results:\n")
        for i, result in enumerate(results, 1):
            print(format_result(result, i))
            print()
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Error: Cannot connect to API at {args.api_url}")
        print("   Is the sound-search-API running? (docker-compose up -d)")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def cmd_search_text(args):
    """Handle search-text command."""
    api = SoundSearchAPI(args.api_url)
    
    print(f"📝 Searching for: \"{args.query}\"")
    print(f"🔍 Retrieving top {args.limit} results...\n")
    
    try:
        response = api.search_sounds(
            text_query=args.query,
            limit=args.limit,
            text_weight=args.text_weight,
            num_frames=args.frames
        )
        
        results = response['results']
        
        if not results:
            print("❌ No results found")
            return
            
        print(f"✅ Found {len(results)} results:\n")
        for i, result in enumerate(results, 1):
            print(format_result(result, i))
            print()
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Error: Cannot connect to API at {args.api_url}")
        print("   Is the sound-search-API running? (docker-compose up -d)")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def cmd_info(args):
    """Handle info command."""
    api = SoundSearchAPI(args.api_url)
    
    print(f"ℹ️  Fetching info for sound ID {args.id}...\n")
    
    try:
        info = api.get_sound_info(args.id)
        
        print(f"ID: {info['id']}")
        print(f"Category: {info['category']}")
        print(f"Description: {info['description']}")
        print(f"File Path: {info['file_path']}")
        print(f"File Name: {os.path.basename(info['file_path'])}")
        
        # Show embedding info if available
        if 'has_text_embedding' in info:
            print(f"\nEmbeddings:")
            print(f"  BASE (512-dim): {'✓' if info.get('has_text_embedding') else '✗'}")
            print(f"  LARGE (768-dim): {'✓' if info.get('has_text_embedding_large') else '✗'}")
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Error: Cannot connect to API at {args.api_url}")
        print("   Is the sound-search-API running? (docker-compose up -d)")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"❌ Error: Sound ID {args.id} not found")
        else:
            print(f"❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def cmd_download(args):
    """Handle download command."""
    api = SoundSearchAPI(args.api_url)
    
    # Ensure output directory exists
    output_dir = args.output or '/tmp/bbc-sounds'
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"📥 Downloading {len(args.ids)} sound(s) to: {output_dir}\n")
    
    downloaded_files = []
    
    for sound_id in args.ids:
        try:
            print(f"  [{sound_id}] Downloading...", end=' ')
            output_file = api.download_sound(sound_id, output_dir)
            downloaded_files.append(output_file)
            print(f"✓ {os.path.basename(output_file)}")
            
        except requests.exceptions.ConnectionError:
            print(f"\n❌ Error: Cannot connect to API at {args.api_url}")
            print("   Is the sound-search-API running? (docker-compose up -d)")
            sys.exit(1)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"✗ Sound ID {sound_id} not found")
            else:
                print(f"✗ Error: {e}")
        except Exception as e:
            print(f"✗ Error: {e}")
            
    if downloaded_files:
        print(f"\n✅ Downloaded {len(downloaded_files)} file(s):")
        for path in downloaded_files:
            print(f"   {path}")
            
        if args.cleanup:
            print(f"\n🗑️  Use the following command to cleanup:")
            print(f"   rm {' '.join(downloaded_files)}")
    else:
        print("\n❌ No files downloaded")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="BBC Sound Search CLI - Semantic audio search powered by X-CLIP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search with video
  %(prog)s search-video /path/to/rain.mp4
  
  # Search with text
  %(prog)s search-text "footsteps on pavement"
  
  # Hybrid search (video + text)
  %(prog)s search-video /path/to/video.mp4 --text "running on gravel"
  
  # Get sound details
  %(prog)s info 5362
  
  # Download sounds
  %(prog)s download 5362 1234 5678
  %(prog)s download 5362 --output /tmp/mysounds/
        """
    )
    
    parser.add_argument(
        '--api-url',
        default=DEFAULT_API_URL,
        help=f'Sound Search API URL (default: {DEFAULT_API_URL})'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # search-video command
    video_parser = subparsers.add_parser(
        'search-video',
        help='Search using video file'
    )
    video_parser.add_argument('video', help='Path to video file')
    video_parser.add_argument(
        '--text',
        help='Additional text query for hybrid search'
    )
    video_parser.add_argument(
        '--limit',
        type=int,
        default=5,
        help='Number of results (default: 5)'
    )
    video_parser.add_argument(
        '--text-weight',
        type=float,
        default=0.6,
        help='Weight for text vs video (0-1, default: 0.6)'
    )
    video_parser.add_argument(
        '--frames',
        type=int,
        default=16,
        help='Number of frames to extract (default: 16)'
    )
    video_parser.set_defaults(func=cmd_search_video)
    
    # search-text command
    text_parser = subparsers.add_parser(
        'search-text',
        help='Search using text description'
    )
    text_parser.add_argument('query', help='Text search query')
    text_parser.add_argument(
        '--limit',
        type=int,
        default=5,
        help='Number of results (default: 5)'
    )
    text_parser.add_argument(
        '--text-weight',
        type=float,
        default=0.6,
        help='Weight for text embedding (default: 0.6)'
    )
    text_parser.add_argument(
        '--frames',
        type=int,
        default=16,
        help='Number of frames (affects model selection, default: 16)'
    )
    text_parser.set_defaults(func=cmd_search_text)
    
    # info command
    info_parser = subparsers.add_parser(
        'info',
        help='Show detailed information for a sound'
    )
    info_parser.add_argument('id', type=int, help='Sound ID')
    info_parser.set_defaults(func=cmd_info)
    
    # download command
    download_parser = subparsers.add_parser(
        'download',
        help='Download sound file(s)'
    )
    download_parser.add_argument(
        'ids',
        type=int,
        nargs='+',
        help='Sound ID(s) to download'
    )
    download_parser.add_argument(
        '--output',
        help=f'Output directory (default: /tmp/bbc-sounds)'
    )
    download_parser.add_argument(
        '--cleanup',
        action='store_true',
        help='Show cleanup command after download'
    )
    download_parser.set_defaults(func=cmd_download)
    
    # Parse and execute
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
        
    args.func(args)


if __name__ == '__main__':
    main()
