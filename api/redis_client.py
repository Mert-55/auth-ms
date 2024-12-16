from typing import Callable, cast

from redis import asyncio as redis_asyncio

from settings import settings

redis: redis_asyncio.Redis = cast(
    Callable[..., redis_asyncio.Redis], redis_asyncio.from_url
)(settings.redis_url, encoding="utf-8", decode_responses=True)
