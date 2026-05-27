"""Duplicate file detection service."""

import hashlib
import logging
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class DuplicateDetector:
    """Duplicate file detector using SHA-256 hashing."""
    
    def __init__(self):
        """Initialize duplicate detector."""
        # In-memory cache for demo (use Redis in production)
        self.hash_cache = {}
        self.cache_ttl_days = 90
    
    def calculate_hash(self, file_data: bytes) -> str:
        """
        Calculate SHA-256 hash of file.
        
        Args:
            file_data: File content as bytes
            
        Returns:
            SHA-256 hash as hex string
        """
        sha256_hash = hashlib.sha256()
        sha256_hash.update(file_data)
        return sha256_hash.hexdigest()
    
    def check_duplicate(self, file_hash: str) -> Optional[dict]:
        """
        Check if file hash exists in cache.
        
        Args:
            file_hash: SHA-256 hash
            
        Returns:
            Cached result if duplicate found, None otherwise
        """
        if file_hash in self.hash_cache:
            cached_entry = self.hash_cache[file_hash]
            
            # Check if cache entry is still valid
            cache_time = cached_entry.get("timestamp")
            if cache_time:
                age = datetime.utcnow() - cache_time
                if age.days < self.cache_ttl_days:
                    logger.info(f"Duplicate file detected: {file_hash}")
                    return cached_entry.get("result")
                else:
                    # Cache expired
                    del self.hash_cache[file_hash]
        
        return None
    
    def store_result(self, file_hash: str, result: dict):
        """
        Store processing result in cache.
        
        Args:
            file_hash: SHA-256 hash
            result: Processing result to cache
        """
        self.hash_cache[file_hash] = {
            "result": result,
            "timestamp": datetime.utcnow()
        }
        logger.info(f"Stored result for hash: {file_hash}")
    
    def force_reprocess(self, file_hash: str):
        """
        Remove hash from cache to force reprocessing.
        
        Args:
            file_hash: SHA-256 hash
        """
        if file_hash in self.hash_cache:
            del self.hash_cache[file_hash]
            logger.info(f"Removed hash from cache: {file_hash}")


# Global duplicate detector instance
duplicate_detector = DuplicateDetector()
