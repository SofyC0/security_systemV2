#!/usr/bin/env python3
"""
Тестирование отправки уведомлений о запасах.
"""

import sys
import os
import logging

logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.inventory_service import inventory_service
from app.core.bot_integration import inventory_bot_integration
from app.telegram_bot.bot import RFIDTelegramBot
import asyncio


async def test_inventory_notifications():
    """Тест отправки уведомлений о запасах"""

    # 1. Создаем тестовые товары с низким запасом
    test_products = [
        {
            "sku": "TEST001",
            "name": "Тестовый товар 1",
            "current_quantity": 3,
            "min_threshold": 10,
            "critical_threshold": 5
        },
        {
            "sku": "TEST002",
            "name": "Тестовый товар 2",
            "current_quantity": 8,
            "min_threshold": 15,
            "critical_threshold": 7
        }
    ]

    logger.info("Добавляем тестовые товары...")
    for product in test_products:
        inventory_service.add_product(
            sku=product["sku"],
            name=product["name"],
            current_quantity=product["current_quantity"],
            min_threshold=product["min_threshold"],
            critical_threshold=product["critical_threshold"]
        )

    # 2. Проверяем запасы
    logger.info("Проверяем запасы...")
    alerts = inventory_service.check_all_products()

    if alerts:
        logger.info(f"Найдено {len(alerts)} оповещений:")
        for alert in alerts:
            logger.info(f" • {alert.message}")

        # 3. Если есть бот, отправляем уведомления
        if inventory_bot_integration.bot:
            logger.info("Отправляем уведомления в Telegram...")
            await inventory_bot_integration.send_inventory_alerts(alerts)
            logger.info("Уведомления отправлены!")
        else:
            logger.warning("Бот не инициализирован. Уведомления не отправлены.")
    else:
        logger.info("Оповещений не найдено.")

    # 4. Очищаем тестовые данные
    logger.info("Очищаем тестовые данные...")
    # Здесь нужно добавить метод удаления тестовых товаров


if __name__ == "__main__":
    # Запускаем тест
    asyncio.run(test_inventory_notifications())