#!/usr/bin/env python3
"""
Ежедневная проверка просроченных товаров.
Можно добавить в планировщик задач (cron).
"""

import sys
import os
import asyncio
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.factories import get_rfid_service
from app.core.logging_config import setup_logging

logger = setup_logging("daily_check")


async def check_expired():
    logger.info("=" * 50)
    logger.info("ПРОВЕРКА ПРОСРОЧЕННЫХ ТОВАРОВ")
    logger.info("=" * 50)

    rfid_service = get_rfid_service()
    expired = await rfid_service.check_expired_items()

    if expired:
        logger.warning(f"Найдено просроченных товаров: {len(expired)}")
        for tag in expired:
            logger.info(f" - {tag}")
    else:
        logger.info("Просроченных товаров не найдено")

    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(check_expired())