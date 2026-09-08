"""
BBC Sound Search API

X-CLIP based video/text to sound retrieval service.
Searches BBC Sound Archive database for matching sound effects.
"""

import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging
from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor

from utils.xclip_encoder import XCLIPEncoder
from utils.db_client import DatabaseClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://bbc_user:change_me@postgres:5432/bbc_sounds"
)
BBC_SOUNDS_PATH = Path(os.getenv("BBC_SOUNDS_PATH", "/sounds"))
MODEL_NAME = os.getenv("XCLIP_MODEL", "microsoft/xclip-base-patch32-16-frames")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Global variables for model and DB
encoder: Optional[XCLIPEncoder] = None
db_client: Optional[DatabaseClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources"""
    global encoder, db_client
    
    logger.info("=" * 60)
    logger.info("BBC Sound Search API Starting...")
    logger.info("=" * 60)
    
    # Initialize X-CLIP encoder
    logger.info(f"Loading X-CLIP model: {MODEL_NAME}")
    logger.info(f"Device: {DEVICE}")
    encoder = XCLIPEncoder(model_name=MODEL_NAME, device=DEVICE)
    logger.info("✓ X-CLIP model loaded successfully")
    
    # Initialize database client
    logger.info(f"Connecting to database: {DATABASE_URL}")
    db_client = DatabaseClient(DATABASE_URL)
    logger.info("✓ Database connected")
    
    # Check database stats
    stats = db_client.get_stats()
    logger.info(f"✓ Available sounds: {stats['available_sounds']}")
    logger.info(f"✓ Sounds with embeddings: {stats['sounds_with_embeddings']}")
    
    if stats['sounds_with_embeddings'] == 0:
        logger.warning("⚠️  No text embeddings found in database!")
        logger.warning("⚠️  Run generate_embeddings.py to create embeddings first")
    
    logger.info("=" * 60)
    logger.info("API Ready!")
    logger.info("=" * 60)
    
    yield
    
    # Cleanup
    logger.info("Shutting down...")
    if db_client:
        db_client.close()


# Create FastAPI app
app = FastAPI(
    title="BBC Sound Search API",
    description="X-CLIP based video/text to sound retrieval",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """API info endpoint"""
    return {
        "service": "BBC Sound Search API",
        "version": "1.0.0",
        "model": MODEL_NAME,
        "device": DEVICE,
        "status": "ready"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        stats = db_client.get_stats()
        return {
            "status": "ok",
            "model": encoder.model_name if encoder else MODEL_NAME,
            "device": DEVICE,
            "database": "connected",
            "available_sounds": stats["available_sounds"],
            "sounds_with_embeddings": stats["sounds_with_embeddings"]
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")


@app.post("/admin/switch-model")
async def switch_model(model_name: str = Form(...)):
    """
    Switch X-CLIP model at runtime.
    
    Supported models:
    - microsoft/xclip-base-patch32 (8 frames)
    - microsoft/xclip-base-patch32-16-frames (16 frames)
    - microsoft/xclip-large-patch14 (8 frames, higher quality)
    - microsoft/xclip-large-patch14-16-frames (16 frames, higher quality)
    
    Args:
        model_name: HuggingFace model identifier
    
    Returns:
        New model info
    """
    global encoder
    
    try:
        logger.info(f"=" * 60)
        logger.info(f"Switching to model: {model_name}")
        
        # Unload old model
        if encoder:
            old_model = encoder.model_name
            del encoder
            torch.cuda.empty_cache()
            logger.info(f"Unloaded: {old_model}")
        
        # Load new model
        encoder = XCLIPEncoder(model_name, DEVICE)
        
        # Update database client to use correct embedding column
        db_client.set_embedding_column(encoder.embedding_dim)
        
        logger.info(f"✓ Model switched: {model_name}")
        logger.info(f"  Embedding dim: {encoder.embedding_dim}")
        logger.info("=" * 60)
        
        return {
            "status": "ok",
            "model": model_name,
            "embedding_dim": encoder.embedding_dim,
            "device": DEVICE
        }
    except Exception as e:
        logger.error(f"❌ Model switch failed: {e}")
        raise HTTPException(status_code=500, detail=f"Model switch failed: {str(e)}")


@app.post("/search/sounds")
async def search_sounds(
    video: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    limit: int = Form(5),
    threshold: float = Form(0.0),
    num_frames: int = Form(16),
    text_weight: float = Form(0.6)
):
    """
    Search BBC sounds by video and/or text using X-CLIP.
    
    Supports hybrid search: video + text prompt with configurable weighting.
    
    Args:
        video: Video file (optional)
        text: Text query/prompt (optional)
        limit: Maximum number of results (default: 5)
        threshold: Minimum similarity threshold 0-1 (default: 0.0)
        num_frames: Number of frames to extract from video (default: 16)
        text_weight: Weight for text prompt when both video+text provided (default: 0.6)
                    Final embedding = (1-text_weight)*video + text_weight*text
    
    Returns:
        List of matching sounds with metadata and similarity scores
    """
    if video is None and text is None:
        raise HTTPException(
            status_code=400,
            detail="Must provide either video or text parameter"
        )
    
    try:
        # Generate query embedding
        if video and text:
            # Hybrid search: video + text prompt
            logger.info(f"Processing hybrid query: video={video.filename}, text='{text}', text_weight={text_weight}")
            video_embedding = await encoder.encode_video(video, num_frames=num_frames)
            text_embedding = encoder.encode_text(text)
            
            # Weighted fusion
            query_embedding = (1 - text_weight) * video_embedding + text_weight * text_embedding
            query_type = f"hybrid (video {1-text_weight:.0%} + text {text_weight:.0%})"
            
        elif video:
            # Video-only search
            logger.info(f"Processing video query: {video.filename}, frames={num_frames}")
            query_embedding = await encoder.encode_video(video, num_frames=num_frames)
            query_type = "video"
        else:
            # Text-only search
            logger.info(f"Processing text query: {text}")
            query_embedding = encoder.encode_text(text)
            query_type = "text"
        
        # Search database
        results = db_client.vector_search(
            query_embedding=query_embedding,
            limit=limit,
            threshold=threshold
        )
        
        logger.info(f"Found {len(results)} results for {query_type} query")
        
        return {
            "query_type": query_type,
            "query": text if text else video.filename,
            "count": len(results),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.get("/sounds/{sound_id}")
async def get_sound_metadata(sound_id: int):
    """
    Get full metadata for a specific sound.
    
    Args:
        sound_id: Database ID of the sound
    
    Returns:
        Sound metadata including file path and all database fields
    """
    try:
        sound = db_client.get_sound_by_id(sound_id)
        if not sound:
            raise HTTPException(status_code=404, detail="Sound not found")
        return sound
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sound {sound_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sounds/{sound_id}/download")
async def download_sound(sound_id: int):
    """
    Download the actual audio file for a sound.
    
    Args:
        sound_id: Database ID of the sound
    
    Returns:
        Audio file as FileResponse
    """
    try:
        sound = db_client.get_sound_by_id(sound_id)
        if not sound:
            raise HTTPException(status_code=404, detail="Sound not found")
        
        # Convert absolute host path to container path
        # DB has: /mnt/data/BBCSoundDownloader/sounds/Category/file.wav
        # Container needs: /sounds/Category/file.wav
        db_path = sound["file_path"]
        if "/BBCSoundDownloader/sounds/" in db_path:
            relative_path = db_path.split("/BBCSoundDownloader/sounds/", 1)[1]
            file_path = Path("/sounds") / relative_path
        else:
            file_path = Path(db_path)
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Audio file not found: {file_path}")
        
        return FileResponse(
            path=file_path,
            media_type="audio/wav",
            filename=file_path.name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download sound {sound_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sounds/{sound_id}/preview")
async def preview_sound(sound_id: int, duration: int = 5):
    """
    Stream a preview of the sound (first N seconds).
    
    Args:
        sound_id: Database ID of the sound
        duration: Preview duration in seconds (default: 5)
    
    Returns:
        Audio stream of first N seconds
    """
    try:
        sound = db_client.get_sound_by_id(sound_id)
        if not sound:
            raise HTTPException(status_code=404, detail="Sound not found")
        
        # Convert absolute host path to container path
        # DB has: /mnt/data/BBCSoundDownloader/sounds/Category/file.wav
        # Container needs: /sounds/Category/file.wav
        db_path = sound["file_path"]
        if "/BBCSoundDownloader/sounds/" in db_path:
            relative_path = db_path.split("/BBCSoundDownloader/sounds/", 1)[1]
            file_path = Path("/sounds") / relative_path
        else:
            file_path = Path(db_path)
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Audio file not found: {file_path}")
        
        # TODO: Implement audio trimming for preview
        # For now, just return the full file
        return FileResponse(
            path=file_path,
            media_type="audio/wav",
            filename=f"preview_{file_path.name}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to preview sound {sound_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_statistics():
    """
    Get database statistics.
    
    Returns:
        Statistics about sounds in database
    """
    try:
        stats = db_client.get_detailed_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/categories")
async def get_categories(limit: int = 50):
    """
    Get list of sound categories.
    
    Args:
        limit: Maximum number of categories to return
    
    Returns:
        List of categories with sound counts
    """
    try:
        categories = db_client.get_categories(limit=limit)
        return {"categories": categories}
    except Exception as e:
        logger.error(f"Failed to get categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
