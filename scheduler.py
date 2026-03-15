#!/usr/bin/env python3
"""
Планировщик для автоматических проверок запасов.
Запускается как отдельный процесс.
"""

import asyncio
import logging
from datetime import datetime, time
from typing import List

from app.core.inventory_service import inventory_service
#from app.telegram_bot.bot import telegram_bot_instance  # Нужно будет создать глобальный экземпляр

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class InventoryScheduler:
    """Планировщик проверок запасов"""

    def __init__(self, bot_instance=None):
        self.bot = bot_instance
        self.running = False

        # Время проверок (можно вынести в настройки)
        self.check_times = [
            time(9, 0),  # Утро
            time(13, 0),  # День
            time(17, 0),  # Вечер
            time(21, 0)  # Ночь
        ]

    async def check_and_notify(self):
        """Проверить запасы и отправить уведомления"""
        # Если нет бота, просто логируем
        if not self.bot:
            logger.info("Проверка запасов завершена. Бот не инициализирован для уведомлений.")
            return

        logger.info("Запуск проверки запасов...")

        try:
            alerts_by_store = inventory_service.check_all_thresholds()

            if not alerts_by_store:
                logger.info("Нет оповещений")
                return

            # Формируем и отправляем сообщения
            for store_name, alerts in alerts_by_store.items():
                message = f"*АВТОМАТИЧЕСКАЯ ПРОВЕРКА ЗАПАСОВ*\n"
                message += f"*{store_name}*\n"
                message += f"{datetime.now().strftime('%H:%M')}\n\n"

                # Группируем оповещения по типу
                critical_alerts = [a for a in alerts if a.alert_type == "critical"]
                warning_alerts = [a for a in alerts if a.alert_type == "warning"]

                if critical_alerts:
                    message += "*ТРЕБУЕТСЯ СРОЧНОЕ ВМЕШАТЕЛЬСТВО:*\n"
                    for i, alert in enumerate(critical_alerts[:5], 1):
                        message += f"{i}. {alert.message}\n"
                    message += "\n"

                if warning_alerts:
                    message += "*РЕКОМЕНДУЕТСЯ ЗАКАЗАТЬ:*\n"
                    for i, alert in enumerate(warning_alerts[:5], 1):
                        message += f"{i}. {alert.message}\n"

                # Отправляем сообщение
                # В реальном приложении нужно отправлять в чат магазина
                # Здесь отправляем всем админам
                await self.bot.send_message_to_all(message)

                logger.info(f"Отправлено уведомление для {store_name}")

        except Exception as e:
            logger.error(f"Ошибка проверки запасов: {e}")

    async def run_scheduler(self):
        """Запуск планировщика"""
        self.running = True
        logger.info("Планировщик запасов запущен")

        while self.running:
            try:
                now = datetime.now().time()
                current_hour_minute = time(now.hour, now.minute)

                # Проверяем, не настало ли время проверки
                for check_time in self.check_times:
                    if (current_hour_minute.hour == check_time.hour and
                            current_hour_minute.minute == check_time.minute):
                        await self.check_and_notify()
                        await asyncio.sleep(60)  # Ждем минуту, чтобы не запускать несколько раз
                        break

                # Ждем 30 секунд перед следующей проверкой
                await asyncio.sleep(30)

            except KeyboardInterrupt:
                logger.info("Остановка планировщика...")
                self.running = False
            except Exception as e:
                logger.error(f"Ошибка в планировщике: {e}")
                await asyncio.sleep(60)


async def main():
    """Основная функция"""
    scheduler = InventoryScheduler()
    await scheduler.run_scheduler()


if __name__ == "__main__":
    asyncio.run(main())