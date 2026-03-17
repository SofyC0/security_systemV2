#!/usr/bin/env python3
"""
Простой скрипт для отправки уведомлений о запасах.
Запуск: python send_inventory_alerts.py
"""

import sys
import os
import asyncio
import logging
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.factories import get_inventory_service
from app.core.logging_config import setup_logging

logger = setup_logging("send_inventory_alerts")
inventory_service = get_inventory_service()


async def send_alerts_to_console():
    parser = argparse.ArgumentParser(description="Проверка и отправка алертов по запасам")
    parser.add_argument("--send", action="store_true", help="Отправить уведомления в Telegram (пока заглушка)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ПРОВЕРКА ЗАПАСОВ ТОВАРОВ")
    logger.info("=" * 60)

    products = await inventory_service.get_all_products()
    logger.info(f"Всего товаров в базе: {len(products)}")

    alerts = await inventory_service.check_all_products()

    if alerts:
        logger.warning(f"НАЙДЕНО ОПОВЕЩЕНИЙ: {len(alerts)}")
        for alert in alerts:
            logger.warning(alert.message)

        if args.send:
            logger.info("Отправка в Telegram запрошена (реализация пока заглушка)")
    else:
        logger.info("Все товары в норме!")
        logger.info("СТАТИСТИКА:")
        for product in products:
            status_icon = "✅"
            if product.get("status") == "critical":
                status_icon = "🚨"
            elif product.get("status") == "warning":
                status_icon = "⚠️"
            logger.info(f"{status_icon} {product['name']}: {product['current_quantity']} {product['unit']} "
                        f"(мин: {product['min_threshold']})")


if __name__ == "__main__":
    asyncio.run(send_alerts_to_console())