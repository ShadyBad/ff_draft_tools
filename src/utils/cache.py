"""
Optimized caching system for Fantasy Football Draft Tools
"""
import gzip
import json
import logging
import os
import pickle
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import hashlib
import shutil

from config import CACHE_DIR


logger = logging.getLogger(__name__)


class CacheStats:
    """Track cache performance statistics"""
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.writes = 0
        self.errors = 0
        self.total_size_bytes = 0
        self.compression_ratio = 0.0
        self._lock = threading.Lock()
    
    def record_hit(self):
        with self._lock:
            self.hits += 1
    
    def record_miss(self):
        with self._lock:
            self.misses += 1
    
    def record_write(self, uncompressed_size: int, compressed_size: int):
        with self._lock:
            self.writes += 1
            self.total_size_bytes += compressed_size
            if uncompressed_size > 0:
                self.compression_ratio = 1.0 - (compressed_size / uncompressed_size)
    
    def record_error(self):
        with self._lock:
            self.errors += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current cache statistics"""
        with self._lock:
            total_requests = self.hits + self.misses
            hit_rate = self.hits / total_requests if total_requests > 0 else 0.0
            
            return {
                'hits': self.hits,
                'misses': self.misses,
                'writes': self.writes,
                'errors': self.errors,
                'hit_rate': hit_rate,
                'total_size_mb': self.total_size_bytes / (1024 * 1024),
                'compression_ratio': self.compression_ratio
            }


class OptimizedCache:
    """Optimized caching system with compression and better management"""
    
    # Global cache stats
    stats = CacheStats()
    
    # Thread locks for concurrent access
    _locks: Dict[str, threading.Lock] = {}
    _locks_lock = threading.Lock()
    
    def __init__(self, namespace: str, cache_hours: int = 24, use_compression: bool = True):
        self.namespace = namespace
        self.cache_hours = cache_hours
        self.use_compression = use_compression
        self.cache_dir = CACHE_DIR / namespace
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Clean up old cache files on init
        self._cleanup_old_files()
    
    def _get_lock(self, key: str) -> threading.Lock:
        """Get or create a lock for a specific cache key"""
        with self._locks_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]
    
    def _get_cache_path(self, key: str) -> Path:
        """Get the cache file path for a key"""
        # Use hash to handle long keys and special characters
        key_hash = hashlib.md5(key.encode()).hexdigest()
        extension = '.pkl.gz' if self.use_compression else '.pkl'
        return self.cache_dir / f"{key_hash}_{key[:20]}{extension}"
    
    def _get_metadata_path(self, cache_path: Path) -> Path:
        """Get metadata file path"""
        return cache_path.with_suffix('.meta')
    
    def set(self, key: str, value: Any, cache_hours: Optional[int] = None) -> bool:
        """Set a value in cache with atomic write"""
        lock = self._get_lock(key)
        
        with lock:
            try:
                cache_path = self._get_cache_path(key)
                meta_path = self._get_metadata_path(cache_path)
                
                # Serialize data
                data = pickle.dumps(value)
                uncompressed_size = len(data)
                
                # Write to temporary file first (atomic write)
                with tempfile.NamedTemporaryFile(dir=self.cache_dir, delete=False) as tmp_file:
                    if self.use_compression:
                        with gzip.open(tmp_file.name, 'wb', compresslevel=6) as gz_file:
                            gz_file.write(data)
                    else:
                        tmp_file.write(data)
                    
                    tmp_path = Path(tmp_file.name)
                
                # Get compressed size
                compressed_size = tmp_path.stat().st_size
                
                # Move temporary file to final location (atomic on most filesystems)
                shutil.move(str(tmp_path), str(cache_path))
                
                # Write metadata
                metadata = {
                    'key': key,
                    'timestamp': datetime.now().isoformat(),
                    'expires': (datetime.now() + timedelta(hours=cache_hours or self.cache_hours)).isoformat(),
                    'uncompressed_size': uncompressed_size,
                    'compressed_size': compressed_size,
                    'compression_ratio': 1.0 - (compressed_size / uncompressed_size) if uncompressed_size > 0 else 0
                }
                
                with open(meta_path, 'w') as f:
                    json.dump(metadata, f)
                
                self.stats.record_write(uncompressed_size, compressed_size)
                logger.debug(f"Cached {key} (compression ratio: {metadata['compression_ratio']:.1%})")
                return True
                
            except Exception as e:
                logger.error(f"Error caching {key}: {e}")
                self.stats.record_error()
                return False
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache"""
        lock = self._get_lock(key)
        
        with lock:
            try:
                cache_path = self._get_cache_path(key)
                meta_path = self._get_metadata_path(cache_path)
                
                # Check if cache exists
                if not cache_path.exists() or not meta_path.exists():
                    self.stats.record_miss()
                    return None
                
                # Check metadata for expiry
                with open(meta_path, 'r') as f:
                    metadata = json.load(f)
                
                expires = datetime.fromisoformat(metadata['expires'])
                if datetime.now() > expires:
                    logger.debug(f"Cache expired for {key}")
                    self.stats.record_miss()
                    # Clean up expired files
                    cache_path.unlink(missing_ok=True)
                    meta_path.unlink(missing_ok=True)
                    return None
                
                # Load data
                if self.use_compression:
                    with gzip.open(cache_path, 'rb') as gz_file:
                        data = gz_file.read()
                else:
                    with open(cache_path, 'rb') as f:
                        data = f.read()
                
                value = pickle.loads(data)
                self.stats.record_hit()
                logger.debug(f"Cache hit for {key}")
                return value
                
            except Exception as e:
                logger.error(f"Error reading cache for {key}: {e}")
                self.stats.record_error()
                return None
    
    def invalidate(self, key: str) -> bool:
        """Invalidate a specific cache entry"""
        lock = self._get_lock(key)
        
        with lock:
            try:
                cache_path = self._get_cache_path(key)
                meta_path = self._get_metadata_path(cache_path)
                
                cache_path.unlink(missing_ok=True)
                meta_path.unlink(missing_ok=True)
                
                logger.debug(f"Invalidated cache for {key}")
                return True
                
            except Exception as e:
                logger.error(f"Error invalidating cache for {key}: {e}")
                return False
    
    def clear_namespace(self) -> int:
        """Clear all cache entries in this namespace"""
        count = 0
        try:
            for file_path in self.cache_dir.iterdir():
                if file_path.is_file():
                    file_path.unlink()
                    count += 1
            
            logger.info(f"Cleared {count} cache files from {self.namespace}")
            return count
            
        except Exception as e:
            logger.error(f"Error clearing cache namespace {self.namespace}: {e}")
            return count
    
    def _cleanup_old_files(self, days: int = 7):
        """Clean up cache files older than specified days"""
        try:
            cutoff_time = datetime.now() - timedelta(days=days)
            cleaned_count = 0
            
            for file_path in self.cache_dir.iterdir():
                if file_path.is_file():
                    # Check file modification time
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_time < cutoff_time:
                        file_path.unlink()
                        cleaned_count += 1
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} old cache files from {self.namespace}")
                
        except Exception as e:
            logger.error(f"Error during cache cleanup: {e}")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about current cache usage"""
        try:
            total_size = 0
            file_count = 0
            oldest_file = None
            newest_file = None
            
            for file_path in self.cache_dir.iterdir():
                if file_path.is_file() and not file_path.suffix == '.meta':
                    file_count += 1
                    total_size += file_path.stat().st_size
                    
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if oldest_file is None or file_time < oldest_file:
                        oldest_file = file_time
                    if newest_file is None or file_time > newest_file:
                        newest_file = file_time
            
            return {
                'namespace': self.namespace,
                'file_count': file_count,
                'total_size_mb': total_size / (1024 * 1024),
                'oldest_file': oldest_file.isoformat() if oldest_file else None,
                'newest_file': newest_file.isoformat() if newest_file else None,
                'stats': self.stats.get_stats()
            }
            
        except Exception as e:
            logger.error(f"Error getting cache info: {e}")
            return {
                'namespace': self.namespace,
                'error': str(e)
            }


# Global cache instances for different data types
rankings_cache = OptimizedCache('rankings', cache_hours=24)
api_cache = OptimizedCache('api_responses', cache_hours=1)
projections_cache = OptimizedCache('projections', cache_hours=48)