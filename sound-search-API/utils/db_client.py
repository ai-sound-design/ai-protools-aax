"""
Database client for BBC Sound Archive PostgreSQL database.
"""

import logging
from typing import List, Dict, Any, Optional
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class DatabaseClient:
    """PostgreSQL client for BBC Sound Archive"""
    
    def __init__(self, database_url: str):
        """
        Initialize database client.
        
        Args:
            database_url: PostgreSQL connection URL
        """
        self.database_url = database_url
        self.embedding_column = "text_embedding"  # Default, can be changed via set_embedding_column()
        self.conn = psycopg2.connect(database_url)
        logger.info(f"Database connection established (using {self.embedding_column})")
    
    def set_embedding_column(self, embedding_dim: int):
        """
        Set embedding column based on model dimension.
        
        Args:
            embedding_dim: Embedding dimension (512 for base, 768 for large)
        """
        if embedding_dim == 768:
            self.embedding_column = "text_embedding_large"
        else:
            self.embedding_column = "text_embedding"
        logger.info(f"Switched to embedding column: {self.embedding_column}")
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get basic database statistics.
        
        Returns:
            Dict with available_sounds and sounds_with_embeddings counts
        """
        with self.conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    COUNT(*) as available_sounds,
                    COUNT(*) FILTER (WHERE text_embedding IS NOT NULL) as sounds_with_embeddings
                FROM available_sounds
            """)
            row = cursor.fetchone()
            return {
                "available_sounds": row[0],
                "sounds_with_embeddings": row[1]
            }
    
    def get_detailed_stats(self) -> Dict[str, Any]:
        """
        Get detailed database statistics.
        
        Returns:
            Dict with comprehensive stats
        """
        with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM sound_stats")
            stats = cursor.fetchone()
            return dict(stats) if stats else {}
    
    def get_categories(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get list of categories with sound counts.
        
        Args:
            limit: Maximum number of categories
        
        Returns:
            List of category dicts
        """
        with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(f"""
                SELECT cdname, total_sounds, available_sounds
                FROM category_stats
                ORDER BY available_sounds DESC
                LIMIT {limit}
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def vector_search(
        self,
        query_embedding: np.ndarray,
        limit: int = 10,
        threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Search for similar sounds using vector similarity.
        
        Args:
            query_embedding: Query embedding vector
            limit: Maximum number of results
            threshold: Minimum similarity threshold (0-1)
        
        Returns:
            List of matching sounds with metadata and similarity scores
        """
        try:
            # Convert numpy array to list for PostgreSQL
            embedding_list = query_embedding.tolist()
            
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Use cosine similarity with pgvector
                # Note: <=> is cosine distance, so 1 - distance = similarity
                query = f"""
                    SELECT 
                        id,
                        location,
                        description,
                        category,
                        cdname,
                        duration_seconds,
                        file_path,
                        1 - ({self.embedding_column} <=> %s::vector) as similarity
                    FROM available_sounds
                    WHERE {self.embedding_column} IS NOT NULL
                        AND (1 - ({self.embedding_column} <=> %s::vector)) >= %s
                    ORDER BY {self.embedding_column} <=> %s::vector
                    LIMIT %s
                """
                cursor.execute(query, (embedding_list, embedding_list, threshold, embedding_list, limit))
                
                results = []
                for row in cursor.fetchall():
                    result = dict(row)
                    # Round similarity to 4 decimals
                    result['similarity'] = round(result['similarity'], 4)
                    results.append(result)
                
                return results
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Vector search failed: {e}")
            raise
    
    def get_sound_by_id(self, sound_id: int) -> Optional[Dict[str, Any]]:
        """
        Get sound metadata by ID.
        
        Args:
            sound_id: Database ID
        
        Returns:
            Sound metadata dict or None if not found
        """
        with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    location,
                    description,
                    category,
                    cdname,
                    cdnumber,
                    tracknum,
                    duration_seconds,
                    file_path,
                    file_exists
                FROM bbc_sounds
                WHERE id = %s
            """, (sound_id,))
            
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
