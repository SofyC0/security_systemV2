#!/usr/bin/env python3
"""
Простой скрипт для отправки уведомлений о запасах.
Запуск: python send_inventory_alerts.py
"""

import sys
import os
import logging
import asyncio
import argparse
logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.factories import get_inventory_service

inventory_service = get_inventory_service()


async def send_alerts_to_console():
    """Выводит оповещения о запасах в консоль + опционально отправляет в TG"""

    # Парсим аргументы командной строки
    parser = argparse.ArgumentParser(description="Проверка и отправка алертов по запасам")
    parser.add_argument("--send", action="store_true",
                        help="Отправить уведомления в Telegram (пока заглушка)")
    args = parser.parse_args()

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
        for alert in alerts:
            logger.warning(alert.message)

        if args.send:
            logger.info("Отправка в Telegram запрошена (реализация пока заглушка)")
            # Здесь в будущем будет реальная отправка через бот
            # Например:
            # await inventory_bot_integration.send_inventory_alerts(alerts)
        else:
            logger.info("Чтобы отправить в Telegram, используйте флаг --send")
            logger.warning("Сейчас вы можете скопировать эти уведомления и отправить вручную.")
    else:
        logger.info("Все товары в норме!")

        # Показываем статистику
        logger.info("СТАТИСТИКА:")
        for product in products:
            status_icon = "✅"
            if product.get("status") == "critical":
                status_icon = "🚨"
            elif product.get("status") == "warning":
                status_icon = "⚠️"

            logger.info(f"{status_icon} {product['name']}: {product['current_quantity']} {product['unit']} "
                        f"(мин: {product['min_threshold']}, крит: {product['critical_threshold']})")


if __name__ == "__main__":
    asyncio.run(send_alerts_to_console())