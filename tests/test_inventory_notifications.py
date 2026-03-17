#!/usr/bin/env python3
"""
Тестирование отправки уведомлений о запасах.
"""

import sys
import os
import asyncio
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.factories import get_inventory_service
from app.core.bot_integration import inventory_bot_integration
from app.core.logging_config import setup_logging

logger = setup_logging("test_inventory_notifications")


async def test_inventory_notifications():
    inventory_service = get_inventory_service()
    inventory_bot_integration.set_inventory_service(inventory_service)

    # Создаём тестовые данные (здесь нужно добавить логику создания/удаления)
    logger.info("Запуск теста уведомлений о запасах...")
    alerts = await inventory_service.check_all_products()

    if alerts:
        logger.info(f"Найдено {len(alerts)} оповещений:")
        for alert in alerts:
            logger.info(f" • {alert.message}")

        if inventory_bot_integration.bot:
            logger.info("Отправляем уведомления в Telegram...")
            await inventory_bot_integration.send_inventory_alerts(alerts)
            logger.info("Уведомления отправлены!")
        else:
            logger.warning("Бот не инициализирован. Уведомления не отправлены.")
    else:
        logger.info("Оповещений не найдено.")

    logger.info("Тест завершён.")


if __name__ == "__main__":
    asyncio.run(test_inventory_notifications())