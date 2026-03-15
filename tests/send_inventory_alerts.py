#!/usr/bin/env python3
"""
Простой скрипт для отправки уведомлений о запасах.
Запуск: python send_inventory_alerts.py
"""

import sys
import os
import logging
logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.inventory_service import inventory_service
import asyncio


async def send_alerts_to_console():
    """Выводит оповещения о запасах в консоль"""
    logger.info("=" * 60)
    logger.info("ПРОВЕРКА ЗАПАСОВ ТОВАРОВ")
    logger.info("=" * 60)

    # 1. Получаем все товары
    products = inventory_service.get_all_products()
    logger.info(f"Всего товаров в базе: {len(products)}")

    # 2. Проверяем пороги
    alerts = inventory_service.check_all_products()

    if alerts:
        logger.warning(f"НАЙДЕНО ОПОВЕЩЕНИЙ: {len(alerts)}")
        logger.warning("-" * 60)
        for alert in alerts:
            logger.warning(alert.message)
        logger.warning("-" * 60)

        # 3. Предлагаем отправить в Telegram
        send_to_tg = input("\nОтправить эти уведомления в Telegram? (y/n): ").strip().lower()

        if send_to_tg == 'y':
            logger.warning("Функция отправки в Telegram будет добавлена позже.")
            logger.warning("Сейчас вы можете скопировать эти уведомления и отправить вручную.")
    else:
        logger.info("Все товары в норме!")

        # Показываем статистику
        logger.info("СТАТИСТИКА:")
        for product in products:
            status_icon = "✅"
            if product["status"] == "critical":
                status_icon = "🚨"
            elif product["status"] == "warning":
                status_icon = "⚠️"

            logger.info(f"{status_icon} {product['name']}: {product['current_quantity']} {product['unit']} "
                  f"(мин: {product['min_threshold']}, крит: {product['critical_threshold']})")


if __name__ == "__main__":
    asyncio.run(send_alerts_to_console())