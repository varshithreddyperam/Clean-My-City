import os
import time
import asyncio
from typing import Tuple, Dict

# Track connection status
redis_client = None
use_redis = False

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

try:
    import redis.asyncio as aioredis
    redis_client = aioredis.from_url(redis_url, decode_responses=True)
    use_redis = True
    print(f"[Cache] Connecting to Redis at {redis_url}...")
except Exception as e:
    print(f"[Cache] Redis client load error: {e}. Falling back to Local Memory Cache.")

class MemoryCache:
    """Thread-safe, async in-memory fallback mimicking Redis expiration keys"""
    def __init__(self):
        self._data: Dict[str, float] = {}  # key -> expiration timestamp
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str:
        async with self._lock:
            exp = self._data.get(key, 0)
            if exp > time.time():
                return "active"
            # Cleanup expired keys on retrieval
            if key in self._data:
                del self._data[key]
            return None

    async def set(self, key: str, value: str, ex: int):
        async with self._lock:
            self._data[key] = time.time() + ex

    async def ttl(self, key: str) -> int:
        async with self._lock:
            exp = self._data.get(key, 0)
            now = time.time()
            if exp > now:
                return int(exp - now)
            return -2  # Redis convention for key does not exist

    async def clear(self):
        async with self._lock:
            self._data.clear()

local_cache = MemoryCache()

async def check_cooldown(username: str, cooldown_seconds: int) -> Tuple[bool, int]:
    """
    Returns (is_allowed, seconds_left).
    Enforces a strict submission cooldown rate limit per user.
    """
    key = f"cooldown:{username}"
    if use_redis:
        try:
            val = await redis_client.get(key)
            if val:
                ttl = await redis_client.ttl(key)
                return False, max(1, ttl)
        except Exception as e:
            print(f"[Cache] Redis error, using memory cache: {e}")
    
    # Fallback to local memory cache
    val = await local_cache.get(key)
    if val:
        ttl = await local_cache.ttl(key)
        return False, max(1, ttl)
        
    return True, 0

async def set_cooldown(username: str, cooldown_seconds: int):
    key = f"cooldown:{username}"
    if use_redis:
        try:
            await redis_client.set(key, "active", ex=cooldown_seconds)
            return
        except Exception as e:
            pass
    await local_cache.set(key, "active", ex=cooldown_seconds)

async def check_duplicate(image_hash: str, spoof_window_seconds: int) -> bool:
    """
    Returns True if the image hash is duplicate (anti-spoofing lock active).
    """
    key = f"hash:{image_hash}"
    if use_redis:
        try:
            val = await redis_client.get(key)
            if val:
                return True
        except Exception as e:
            pass
    
    val = await local_cache.get(key)
    return val is not None

async def set_duplicate_lock(image_hash: str, spoof_window_seconds: int):
    key = f"hash:{image_hash}"
    if use_redis:
        try:
            await redis_client.set(key, "active", ex=spoof_window_seconds)
            return
        except Exception as e:
            pass
    await local_cache.set(key, "active", ex=spoof_window_seconds)

async def clear_cache():
    if use_redis:
        try:
            await redis_client.flushdb()
        except Exception as e:
            pass
    await local_cache.clear()
