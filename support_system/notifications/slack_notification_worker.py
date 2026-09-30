"""
Generic notification worker.
Reads workspace-aware events from the Redis 'notifications_queue' and
dispatches them to the correct provider via notification_dispatcher.dispatch().

Run with:
    uv run python support_system/notifications/slack_notification_worker.py
"""
import asyncio
import json
import logging
import os
from uuid import UUID

import redis
from dotenv import load_dotenv

load_dotenv(override=True)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("notification_worker")


async def consume() -> None:
    from backend.db.base import async_session
    from backend.services.notification_dispatcher import dispatch

    logger.info("Notification worker started. Listening on 'notifications_queue'...")

    while True:
        try:
            result = redis_client.brpop("notifications_queue", timeout=5)
            if result:
                _, raw = result
                msg = json.loads(raw)
                workspace_id = UUID(msg["workspace_id"])
                event_type   = msg["event_type"]
                payload      = msg["payload"]

                async with async_session() as db:
                    await dispatch(event_type, workspace_id, payload, db)

        except Exception as exc:
            logger.error("Worker error: %s", exc, exc_info=True)
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(consume())