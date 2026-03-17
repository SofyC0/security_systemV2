#!/usr/bin/env python3

import sys
import asyncio
from datetime import datetime, timedelta

sys.path.append('.')

from app.core.database import db
from arduino_reader import SerialRFIDReader
from app.telegram_bot.bot import RFIDTelegramBot
from app.core.services import AlarmManager, RFIDService
from app.core.inventory_service import InventoryService
from app.core.models import CatalogProduct, TaggedItem
from config.settings import settings
from app.core.logging_config import setup_logging

logger = setup_logging("main")


class RFIDStoreSystem:
    def __init__(self):
        logger.info("=" * 60)
        logger.info("RFID СИСТЕМА УПРАВЛЕНИЯ МАГАЗИНОМ С TELEGRAM БОТОМ")
        logger.info("=" * 60)

        self.db = db
        self.alarm_manager = AlarmManager()
        self.inventory_service = InventoryService(db=self.db)
        self.rfid_service = RFIDService(
            db=self.db,
            alarm_manager=self.alarm_manager,
            telegram_bot=None  # будет установлен после создания бота
        )
        # Устанавливаем ссылку на inventory_service в rfid_service
        self.rfid_service.inventory_service = self.inventory_service

        self.reader = SerialRFIDReader()
        self.tg_bot = None
        self.running = False
        self.scan_count = 0
        self.alarm_count = 0
        self.check_interval = 3
        self.daily_check_hour = 3
        self.last_daily_check = datetime.now()
        self.last_inventory_check = datetime.now()
        self.inventory_check_interval = timedelta(hours=6)

    async def initialize(self) -> bool:
        logger.info("=" * 60)
        logger.info("1. ИНИЦИАЛИЗАЦИЯ СИСТЕМЫ")
        logger.info("=" * 60)

        try:
            logger.info("Подключение RFID-считывателя...")
            if not await asyncio.to_thread(self.reader.connect):
                logger.warning("Не удалось подключить RFID-считыватель")
                return False
            logger.info("RFID-считыватель подключен")

            logger.info("Инициализация Telegram бота...")
            if not await self.init_telegram_bot():
                logger.warning("Telegram бот не инициализирован, система будет работать без уведомлений")
            else:
                logger.info("Telegram бот готов к работе")

            logger.info("Проверка базы данных...")
            try:
                stats = await self.rfid_service.get_system_stats()
                logger.info(f"База данных подключена. Товаров: {stats.get('total_items', 0)}")
            except Exception as e:
                logger.error(f"Ошибка при проверке БД: {e}")

            # Проверка просроченных товаров при запуске
            await self.rfid_service.check_expired_items()

            logger.info("=" * 60)
            logger.info("СИСТЕМА ИНИЦИАЛИЗИРОВАНА")
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.critical(f"Критическая ошибка инициализации: {e}")
            return False

    async def init_telegram_bot(self) -> bool:
        try:
            if not settings.BOT_TOKEN:
                logger.warning("Токен бота не задан в .env")
                return False

            self.tg_bot = RFIDTelegramBot(
                token=settings.BOT_TOKEN,
                admin_chat_ids=settings.ADMIN_CHAT_IDS,
                inventory_service=self.inventory_service,
                rfid_service=self.rfid_service
            )
            self.rfid_service.telegram_bot = self.tg_bot

            # Запускаем бота в текущем цикле событий
            asyncio.create_task(self.tg_bot.start())

            logger.info("Telegram бот инициализирован и передан в RFIDService")
            return True
        except Exception as e:
            logger.error(f"Ошибка инициализации бота: {e}")
            return False

    async def _trigger_alarm(self, unpaid_items: list):
        logger.info("ВКЛЮЧЕНА СИГНАЛИЗАЦИЯ!")
        if len(unpaid_items) == 1:
            item = unpaid_items[0]
            message = (f"*ТРЕВОГА!*\n"
                       f"Обнаружен неоплаченный товар:\n"
                       f"• {item['name']}\n"
                       f"• RFID: `{item['rfid']}`")
        else:
            message = f"*ТРЕВОГА!*\nОбнаружено {len(unpaid_items)} неоплаченных товаров:\n"
            for item in unpaid_items:
                message += f"• {item['name']} (`{item['rfid']}`)\n"

        await self.rfid_service.send_telegram_notification(message, "alarm")
        logger.info("Ожидание 5 секунд...")
        await asyncio.sleep(5)
        logger.info("Сигнализация выключена")

    async def process_antenna_reading(self):
        current_time = datetime.now().strftime('%H:%M:%S')
        try:
            detected_tags = await asyncio.to_thread(self.reader.read_tags)
            self.scan_count += 1

            if not detected_tags:
                if self.scan_count % 10 == 0:
                    logger.info("Меток не обнаружено")
                return

            logger.info(f"Сканирование #{self.scan_count}")
            logger.info(f"Обнаружено меток: {len(detected_tags)}")
            logger.info(f"Метки: {detected_tags}")

            unpaid_items = []
            for rfid in detected_tags:
                item_info = await self.rfid_service.search_item(rfid)
                if item_info and item_info.get('status') == 'не_оплачен':
                    unpaid_items.append({'rfid': rfid, 'name': item_info.get('name', 'Неизвестный товар')})
                elif not item_info:
                    unpaid_items.append({'rfid': rfid, 'name': 'Неизвестный товар (не в БД)'})

            if unpaid_items:
                self.alarm_count += 1
                await self._trigger_alarm(unpaid_items)
            else:
                logger.info("Все товары оплачены или просрочены")

        except Exception as e:
            logger.error(f"Ошибка обработки сканирования: {e}")

    async def run_continuous_mode(self):
        logger.info("=" * 60)
        logger.info("НЕПРЕРЫВНЫЙ РЕЖИМ РАБОТЫ МАГАЗИНА")
        logger.info("=" * 60)
        logger.info("Система работает. Нажмите Ctrl+C для остановки.\n")

        self.running = True

        try:
            while self.running:
                await self.process_antenna_reading()

                now = datetime.now()
                # Ежедневная проверка просрочки
                if now.hour == self.daily_check_hour and now.date() != self.last_daily_check.date():
                    logger.info("\n" + "=" * 40)
                    logger.info("ЕЖЕДНЕВНАЯ ПРОВЕРКА ПРОСРОЧКИ")
                    logger.info("=" * 40)
                    expired = await self.rfid_service.check_expired_items()
                    logger.info(f"Найдено просроченных товаров: {len(expired)}")
                    self.last_daily_check = now
                    logger.info("=" * 40 + "\n")

                # Периодическая проверка запасов
                if now - self.last_inventory_check > self.inventory_check_interval:
                    logger.info("Периодическая проверка запасов...")
                    await self.rfid_service.check_all_conditions()
                    self.last_inventory_check = now

                if self.scan_count % 20 == 0:
                    await self.show_mini_stats()

                await asyncio.sleep(self.check_interval)

        except asyncio.CancelledError:
            logger.info("Остановка непрерывного режима...")
            self.running = False
            self.reader.disconnect()

    async def show_mini_stats(self):
        stats = await self.rfid_service.get_system_stats()
        logger.info("=" * 40)
        logger.info("МИНИ-СТАТИСТИКА")
        logger.info("=" * 40)
        logger.info(f"Сканирований: {self.scan_count} | Тревог: {self.alarm_count}")
        logger.info(f"Товаров: {stats.get('total_items', 0)} | Не оплачено: {stats.get('not_paid_items', 0)}")
        logger.info(f"Telegram бот: {'Y' if self.tg_bot else 'N'}")
        logger.info("=" * 40)

    # Остальные методы меню (show_main_menu, show_system_stats, search_item_menu и т.д.)
    # должны быть переписаны на асинхронные, но для краткости здесь опущены.
    # В реальном проекте их нужно адаптировать аналогично, используя await при вызове сервисов
    # и asyncio.to_thread для input().

    async def run(self):
        """Главный асинхронный цикл программы"""
        try:
            while True:
                self.show_main_menu()  # синхронный вывод меню
                try:
                    choice = await asyncio.to_thread(input, "\nВыберите действие (0-7): ")
                except (EOFError, KeyboardInterrupt):
                    logger.info("Ввод прерван")
                    break

                choice = choice.strip()
                if not choice:
                    continue

                if choice == "0":
                    logger.info("Завершение работы системы...")
                    if self.tg_bot:
                        await self.tg_bot.stop()
                    self.running = False
                    break
                elif choice == "1":
                    await self.run_continuous_mode()
                elif choice == "2":
                    await self.run_demo_mode()
                elif choice == "3":
                    await self.show_system_stats()
                    await asyncio.to_thread(input, "Нажмите Enter для продолжения...")
                elif choice == "4":
                    await self.search_item_menu()
                elif choice == "5":
                    await self.inventory_management_menu()
                elif choice == "6":
                    await self.telegram_bot_menu()
                    await asyncio.to_thread(input, "Нажмите Enter для продолжения...")
                elif choice == "7":
                    await self.show_settings_menu()
                else:
                    logger.info(f"Неверный выбор: '{choice}'")
        except Exception as e:
            logger.error(f"Критическая ошибка в главном цикле: {e}")
        finally:
            logger.info("Программа завершена")

    def show_main_menu(self):
        logger.info("=" * 60)
        logger.info("ГЛАВНОЕ МЕНЮ - RFID СИСТЕМА УПРАВЛЕНИЯ МАГАЗИНОМ")
        logger.info("=" * 60)
        menu_items = [
            "1. Запустить непрерывный режим работы",
            "2. Демонстрационный режим (сценарии)",
            "3. Показать статистику системы",
            "4. Поиск товара по RFID",
            "5. Управление запасами товаров",
            "6. Управление Telegram ботом",
            "7. Настройки системы",
            "0. Выход"
        ]
        for item in menu_items:
            logger.info(item)
        logger.info("=" * 60)

    # Остальные методы-заглушки для меню (не реализованы полностью, но можно дополнить)
    async def run_demo_mode(self):
        logger.info("Демо-режим пока не реализован в асинхронной версии")
        await asyncio.sleep(1)

    async def show_system_stats(self):
        stats = await self.rfid_service.get_system_stats()
        logger.info("=" * 60)
        logger.info("ПОДРОБНАЯ СТАТИСТИКА СИСТЕМЫ")
        logger.info("=" * 60)
        logger.info(f"Товаров: {stats.get('total_items', 0)}")
        logger.info(f"Не оплачено: {stats.get('not_paid_items', 0)}")
        logger.info(f"Оплачено: {stats.get('paid_items', 0)}")
        logger.info(f"Просрочено: {stats.get('expired_items', 0)}")
        active = self.rfid_service.alarm_manager.get_active_alarms()
        logger.info(f"Активных тревог: {len(active)}")
        logger.info("=" * 60)

    async def search_item_menu(self):
        logger.info("Поиск товара по RFID (заглушка)")

    async def inventory_management_menu(self):
        logger.info("Управление запасами (заглушка)")

    async def telegram_bot_menu(self):
        logger.info("Управление Telegram ботом (заглушка)")

    async def show_settings_menu(self):
        logger.info("Настройки (заглушка)")


async def main():
    logger.info("=" * 60)
    logger.info("ЗАПУСК RFID СИСТЕМЫ С TELEGRAM БОТОМ")
    logger.info("=" * 60)

    system = RFIDStoreSystem()
    if not await system.initialize():
        logger.error("Не удалось инициализировать систему")
        sys.exit(1)

    await system.run()


if __name__ == "__main__":
    asyncio.run(main())