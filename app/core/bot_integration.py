#!/usr/bin/env python3
"""
Интеграция бота Telegram с сервисом управления запасами.
"""

import asyncio
import logging
from typing import List

from app.core.inventory_service import InventoryAlert

logger = logging.getLogger(__name__)


class InventoryBotIntegration:
    """Интеграция управления запасами с Telegram ботом"""

    def __init__(self, telegram_bot=None):
        self.bot = telegram_bot
        self.inventory_service = None  # будет установлен позже

    def set_bot(self, telegram_bot):
        self.bot = telegram_bot

    def set_inventory_service(self, inventory_service):
        self.inventory_service = inventory_service

    async def send_inventory_alerts(self, alerts: List[InventoryAlert]):
        """Отправить оповещения о запасах в Telegram"""
        if not self.bot or not alerts:
            return

        for alert in alerts:
            try:
                await self.bot.send_message_to_all(alert.message)
                logger.info(f"Отправлено оповещение: {alert.product_name}")
            except Exception as e:
                logger.error(f"Ошибка отправки оповещения: {e}")

    async def check_and_notify(self):
        """Проверить запасы и отправить уведомления (асинхронная версия)"""
        if not self.inventory_service or not self.bot:
            logger.warning("Inventory service или бот не установлены")
            return []
        alerts = await self.inventory_service.check_all_products()
        if alerts:
            await self.send_inventory_alerts(alerts)
        return alerts


# Глобальный экземпляр интеграции
inventory_bot_integration = InventoryBotIntegration()