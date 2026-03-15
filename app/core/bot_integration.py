#!/usr/bin/env python3
"""
Интеграция бота Telegram с сервисом управления запасами.
"""

import asyncio
import logging
from typing import List
from app.core.inventory_service import InventoryAlert, inventory_service
from app.telegram_bot.bot import RFIDTelegramBot

logger = logging.getLogger(__name__)


class InventoryBotIntegration:
    """Интеграция управления запасами с Telegram ботом"""

    def __init__(self, telegram_bot: RFIDTelegramBot = None):
        self.bot = telegram_bot
        self.inventory_service = inventory_service

    def set_bot(self, telegram_bot: RFIDTelegramBot):
        """Установить бота для отправки уведомлений"""
        self.bot = telegram_bot

    async def send_inventory_alerts(self, alerts: List[InventoryAlert]):
        """Отправить оповещения о запасах в Telegram"""
        if not self.bot or not alerts:
            return

        for alert in alerts:
            try:
                # Отправляем сообщение всем администраторам
                await self.bot.send_message_to_all(alert.message)
                logger.info(f"Отправлено оповещение: {alert.product_name}")
            except Exception as e:
                logger.error(f"Ошибка отправки оповещения: {e}")

    def check_and_notify(self):
        """Проверить запасы и отправить уведомления (синхронная версия)"""
        alerts = self.inventory_service.check_all_products()
        if alerts and self.bot:
            # Запускаем асинхронную отправку
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.send_inventory_alerts(alerts))
            except Exception as e:
                logger.error(f"Ошибка отправки уведомлений: {e}")
        return alerts


# Глобальный экземпляр интеграции
inventory_bot_integration = InventoryBotIntegration()