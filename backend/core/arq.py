from arq import create_pool
from arq.connections import RedisSettings
from backend.core.config import settings

_pool = None

async def get_arq_redis():
    global _pool
    if _pool:
        return _pool
        
    redis_url = settings.REDIS_URL
    host = "localhost"
    port = 6379
    database = 0
    if "redis://" in redis_url:
        parts = redis_url.replace("redis://", "").split("/")
        host_port = parts[0].split(":")
        host = host_port[0]
        if len(host_port) > 1:
            port = int(host_port[1])
        if len(parts) > 1 and parts[1]:
            database = int(parts[1])
            
    _pool = await create_pool(RedisSettings(host=host, port=port, database=database))
    return _pool
