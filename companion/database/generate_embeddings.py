#!/usr/bin/env python3
"""
Generate X-CLIP text embeddings for BBC Sound Archive descriptions.

This script:
1. Loads X-CLIP text encoder
2. Reads all sound descriptions from available_sounds view
3. Generates text embeddings in batches
4. Updates text_embedding column in database
5. Creates vector index for fast similarity search

Run this ONCE after database is populated with sounds.

Usage:
    python generate_embeddings.py           # Generate base embeddings (512-dim)
    python generate_embeddings.py --large   # Generate large embeddings (768-dim)
"""

import os
import sys
import argparse
from pathlib import Path
import logging
from typing import List, Tuple
import time

import torch
import numpy as np
from transformers import AutoModel, AutoProcessor
import psycopg2
from psycopg2.extras import execute_batch

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://bbc_user:change_me@localhost:5432/bbc_sounds"
)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
BATCH_SIZE = 32  # Process this many descriptions at once

# Model configurations
MODEL_CONFIGS = {
    'base': {
        'name': 'microsoft/xclip-base-patch32',
        'column': 'text_embedding',
        'dimension': 512,
        'index': 'idx_text_emb'
    },
    'large': {
        'name': 'microsoft/xclip-large-patch14',
        'column': 'text_embedding_large',
        'dimension': 768,
        'index': 'idx_text_emb_large'
    }
}


class XCLIPTextEncoder:
    """X-CLIP text encoder for generating embeddings"""
    
    def __init__(self, model_name: str, device: str = DEVICE):
        """Initialize X-CLIP text encoder"""
        logger.info(f"Loading X-CLIP model: {model_name}")
        logger.info(f"Device: {device}")
        
        self.device = device
        self.processor = AutoProcessor.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(device)
        self.model.eval()
        
        logger.info("✓ X-CLIP model loaded")
        
        # Get embedding dimension
        with torch.no_grad():
            dummy = self.processor(text=["test"], return_tensors="pt", padding=True)
            dummy_output = self.model.get_text_features(**{k: v.to(device) for k, v in dummy.items()})
            self.embedding_dim = dummy_output.shape[-1]
        
        logger.info(f"Embedding dimension: {self.embedding_dim}")
    
    def encode_batch(self, texts: List[str]) -> np.ndarray:
        """
        Encode a batch of texts to embeddings.
        
        Args:
            texts: List of text strings
        
        Returns:
            Normalized embeddings as numpy array (batch_size, embedding_dim)
        """
        with torch.no_grad():
            inputs = self.processor(text=texts, return_tensors="pt", padding=True, truncation=True)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            text_features = self.model.get_text_features(**inputs)
            
            # Normalize
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            
            return text_features.cpu().numpy()


def ensure_column_exists(conn, column_name: str, dimension: int):
    """Ensure embedding column exists in database"""
    with conn.cursor() as cursor:
        cursor.execute(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'bbc_sounds' AND column_name = '{column_name}'
        """)
        
        if not cursor.fetchone():
            logger.info(f"Creating column {column_name} with dimension {dimension}...")
            cursor.execute(f"""
                ALTER TABLE bbc_sounds 
                ADD COLUMN {column_name} vector({dimension})
            """)
            conn.commit()
            logger.info(f"✓ Column {column_name} created")
        else:
            logger.info(f"✓ Column {column_name} exists")


def fetch_sounds_to_encode(conn, column_name: str) -> List[Tuple[int, str]]:
    """
    Fetch all sounds that need embeddings.
    
    Args:
        column_name: Name of embedding column to check
    
    Returns:
        List of (id, text) tuples where text = "{category}: {description}"
    """
    with conn.cursor() as cursor:
        cursor.execute(f"""
            SELECT id, 
                   CASE 
                       WHEN category IS NOT NULL AND category != '' AND category != 'N/A' 
                       THEN category || ': ' || description
                       ELSE description
                   END as text
            FROM bbc_sounds
            WHERE file_exists = TRUE
              AND {column_name} IS NULL
            ORDER BY id
        """)
        return cursor.fetchall()


def update_embeddings_batch(conn, embeddings_data: List[Tuple], column_name: str):
    """
    Update embeddings in database (batch operation).
    
    Args:
        embeddings_data: List of (embedding_list, sound_id) tuples
        column_name: Name of embedding column to update
    """
    with conn.cursor() as cursor:
        execute_batch(cursor, f"""
            UPDATE bbc_sounds
            SET {column_name} = %s::vector
            WHERE id = %s
        """, embeddings_data, page_size=100)
        conn.commit()


def create_vector_index(conn, column_name: str, index_name: str):
    """Create vector index for fast similarity search"""
    logger.info("Creating vector index for fast search...")
    
    with conn.cursor() as cursor:
        # Check if index already exists
        cursor.execute(f"""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'bbc_sounds' AND indexname = '{index_name}'
        """)
        
        if cursor.fetchone():
            logger.info("Index already exists, skipping...")
            return
        
        # Create IVFFlat index (approximate nearest neighbor)
        # lists parameter: sqrt(row_count) is a good default
        cursor.execute(f"""
            CREATE INDEX {index_name} ON bbc_sounds
            USING ivfflat ({column_name} vector_cosine_ops)
            WITH (lists = 100);
        """)
        conn.commit()
        logger.info("✓ Vector index created")


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Generate X-CLIP text embeddings for BBC Sound Archive'
    )
    parser.add_argument(
        '--large',
        action='store_true',
        help='Use X-CLIP large model (768-dim) instead of base (512-dim)'
    )
    return parser.parse_args()


def main():
    """Main embedding generation function"""
    # Parse arguments
    args = parse_args()
    
    # Select model configuration
    model_type = 'large' if args.large else 'base'
    config = MODEL_CONFIGS[model_type]
    
    logger.info("=" * 80)
    logger.info("BBC Sound Archive - Text Embedding Generation")
    logger.info(f"Model: {config['name']} ({model_type})")
    logger.info(f"Column: {config['column']} (dimension: {config['dimension']})")
    logger.info("=" * 80)
    logger.info("")
    
    start_time = time.time()
    
    # Connect to database
    logger.info("Connecting to database...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        logger.info("✓ Database connected")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return 1
    
    try:
        # Ensure column exists
        ensure_column_exists(conn, config['column'], config['dimension'])
        logger.info("")
        
        # Fetch sounds to encode
        logger.info("Fetching sounds from database...")
        sounds_to_encode = fetch_sounds_to_encode(conn, config['column'])
        total_sounds = len(sounds_to_encode)
        
        if total_sounds == 0:
            logger.info("✓ All sounds already have embeddings!")
            return 0
        
        logger.info(f"Found {total_sounds} sounds to encode")
        logger.info("")
        
        # Initialize encoder
        encoder = XCLIPTextEncoder(config['name'], DEVICE)
        logger.info("")
        
        # Process in batches
        logger.info(f"Processing in batches of {BATCH_SIZE}...")
        logger.info("=" * 80)
        
        processed = 0
        batch_ids = []
        batch_texts = []
        
        for sound_id, description in sounds_to_encode:
            batch_ids.append(sound_id)
            batch_texts.append(description)
            
            # Process batch when full
            if len(batch_texts) >= BATCH_SIZE:
                # Generate embeddings
                embeddings = encoder.encode_batch(batch_texts)
                
                # Prepare data for database update
                embeddings_data = [
                    (emb.tolist(), sound_id)
                    for emb, sound_id in zip(embeddings, batch_ids)
                ]
                
                # Update database
                update_embeddings_batch(conn, embeddings_data, config['column'])
                
                processed += len(batch_texts)
                progress = processed / total_sounds * 100
                logger.info(f"Progress: {processed}/{total_sounds} ({progress:.1f}%)")
                
                # Clear batch
                batch_ids = []
                batch_texts = []
        
        # Process remaining sounds
        if batch_texts:
            embeddings = encoder.encode_batch(batch_texts)
            embeddings_data = [
                (emb.tolist(), sound_id)
                for emb, sound_id in zip(embeddings, batch_ids)
            ]
            update_embeddings_batch(conn, embeddings_data, config['column'])
            processed += len(batch_texts)
        
        logger.info("=" * 80)
        logger.info(f"✓ Processed {processed} sounds")
        logger.info("")
        
        # Create vector index
        create_vector_index(conn, config['column'], config['index'])
        logger.info("")
        
        # Final statistics
        elapsed = time.time() - start_time
        logger.info("=" * 80)
        logger.info("COMPLETED!")
        logger.info("=" * 80)
        logger.info(f"Total sounds encoded: {processed}")
        logger.info(f"Model: {config['name']}")
        logger.info(f"Embedding dimension: {encoder.embedding_dim}")
        logger.info(f"Column: {config['column']}")
        logger.info(f"Time elapsed: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
        logger.info(f"Average: {elapsed/processed:.2f} seconds per sound")
        logger.info("")
        logger.info("✓ Database ready for vector search!")
        logger.info("✓ You can now use the sound-search-API")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Error during embedding generation: {e}", exc_info=True)
        return 1
    finally:
        conn.close()
        logger.info("Database connection closed")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
