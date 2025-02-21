from fastapi import HTTPException
import asyncio
import redis.exceptions
import redis.asyncio as redis

REDIS_URL = "redis://redis:6379/0"


async def get_redis():
    redis_client = redis.Redis.from_url(
        REDIS_URL, decode_responses=True, max_connections=500
    )
    try:
        yield redis_client
    finally:
        await redis_client.aclose()


async def get_redis_session():
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


async def redis_execute(redis_client, command, *args, retries=3, delay=0.5):
    for _ in range(retries):
        try:
            return await getattr(redis_client, command)(*args)
        except redis.exceptions.ConnectionError as e:
            if _ == retries - 1:
                raise HTTPException(status_code=500, detail=f"Redis Error: {str(e)}")
            await asyncio.sleep(delay)  
