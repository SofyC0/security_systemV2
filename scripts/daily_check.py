#!/usr/bin/env python3
"""
Ежедневная проверка просроченных товаров.
Можно добавить в планировщик задач (cron).
"""

import sys
import os
import logging
logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.services import RFIDService
from app.telegram_bot.bot import RFIDTelegramBot

def check_expired():
    """Проверка и обновление просроченных товаров"""
    logger.info("=" * 50)
    logger.info("ПРОВЕРКА ПРОСРОЧЕННЫХ ТОВАРОВ")
    logger.info("=" * 50)

    service = RFIDService()
    expired = service.check_expired_items()

    if expired:
        logger.warning(f"Найдено просроченных товаров: {len(expired)}")
        for tag in expired:
            logger.info(f" - {tag}")
    else:
        logger.info("Просроченных товаров не найдено")

    logger.info("=" * 50)


if __name__ == "__main__":
    check_expired()