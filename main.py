#!/usr/bin/env python3

import sys
import time
import threading
import asyncio
from datetime import datetime


sys.path.append('.')

from app.core.database import db
from arduino_reader import SerialRFIDReader
from app.telegram_bot.bot import RFIDTelegramBot
from app.core.services import AlarmManager
from app.core.services import RFIDService
from app.core.inventory_service import InventoryService
import app.core.inventory_service
import app.core.services
from app.core.models import TaggedItem
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
            telegram_bot=None  # пока None, установим после создания бота
        )

        self.reader = SerialRFIDReader()
        self.tg_bot = None
        self.tg_bot_thread = None
        self.running = False
        self.scan_count = 0
        self.alarm_count = 0
        self.check_interval = 3
        self.daily_check_hour = 3
        self.hourly_check_interval = 6

        #self.inventory_service = InventoryService(db=self.db)
        self.rfid_service = RFIDService(db=self.db, alarm_manager=self.alarm_manager, telegram_bot=None)

        # Устанавливаем глобальные ссылки для бота
        import app.core.inventory_service
        import app.core.services
        app.core.inventory_service.inventory_service = self.inventory_service
        app.core.services.rfid_service = self.rfid_service

    def initialize(self) -> bool:
        logger.info("=" * 60)
        logger.info("1. ИНИЦИАЛИЗАЦИЯ СИСТЕМЫ")
        logger.info("=" * 60)

        try:
            logger.info("Подключение RFID-считывателя...")
            if not self.reader.connect():
                logger.warning("Не удалось подключить RFID-считыватель")
                return False
            logger.warning("RFID-считыватель подключен")

            logger.info("Инициализация Telegram бота...")
            if not self.init_telegram_bot():
                logger.warning("Telegram бот не инициализирован, система будет работать без уведомлений")
            else:
                logger.info("Telegram бот готов к работе")

            logger.info("Проверка базы данных...")
            try:
                stats = self.rfid_service.get_system_stats()
                logger.info(f"База данных подключена. Товаров: {stats.get('total_items', 0)}")
            except Exception as e:
                logger.error(f"Ошибка при проверке БД: {e}")

            # При запуске проверим просроченные товары и отправим уведомления
            self.rfid_service.check_expired_items()

            logger.info("=" * 60)
            logger.info("СИСТЕМА ИНИЦИАЛИЗИРОВАНА")
            logger.info("=" * 60)

            return True

        except Exception as e:
            logger.critical(f"Критическая ошибка инициализации: {e}")
            return False

    def init_telegram_bot(self) -> bool:
        try:
            BOT_TOKEN = settings.BOT_TOKEN
            ADMIN_CHAT_IDS = settings.ADMIN_CHAT_IDS

            if not BOT_TOKEN:
                logger.warning("Токен бота не задан в .env")
                return False

            self.tg_bot = RFIDTelegramBot(
                token=BOT_TOKEN,
                admin_chat_ids=ADMIN_CHAT_IDS,
                inventory_service=self.inventory_service,
                rfid_service=self.rfid_service
            )

            # Передаём бота в rfid_service для отправки уведомлений
            self.rfid_service.telegram_bot = self.tg_bot

            self.tg_bot_thread = threading.Thread(target=self.run_telegram_bot, daemon=True)
            self.tg_bot_thread.start()

            logger.info("Telegram бот инициализирован и передан в RFIDService")
            return True
        except Exception as e:
            logger.error(f"Ошибка инициализации бота: {e}")
            return False

    def run_telegram_bot(self):
        if not self.tg_bot:
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.tg_bot.loop = loop

        try:
            loop.run_until_complete(self.tg_bot.start())
            loop.run_until_complete(self.tg_bot.send_message_to_all(
                "*Система мониторинга магазина запущена!*\n"
                f"Время: {datetime.now().strftime('%H:%M:%S')}"
            ))
            loop.run_forever()
        except KeyboardInterrupt:
            logger.debug("Остановка Telegram бота...")
        except Exception as e:
            logger.error(f"Ошибка в Telegram боте: {e}")
        finally:
            if loop.is_running():
                loop.stop()
            loop.close()

    def _trigger_alarm(self, unpaid_items: list) -> None:
        """Включение сигнализации и отправка уведомлений"""
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

        # Отправляем через сервис (асинхронно)
        asyncio.run_coroutine_threadsafe(
            self.rfid_service.send_telegram_notification(message, "alarm"),
            self.tg_bot.loop
        )

        logger.info("Ожидание 5 секунд...")
        time.sleep(5)
        logger.info("Сигнализация выключена")

    def process_antenna_reading(self) -> None:
        """Обработка показаний антенны"""
        current_time = datetime.now().strftime('%H:%M:%S')
        try:
            detected_tags = self.reader.read_tags()
            self.scan_count += 1

            if not detected_tags:
                if self.scan_count % 10 == 0:
                    logger.info(f"Меток не обнаружено")
                return

            logger.info(f"Сканирование #{self.scan_count}")
            logger.info(f"Обнаружено меток: {len(detected_tags)}")
            logger.info(f"Метки: {detected_tags}")

            unpaid_items = []
            for rfid in detected_tags:
                item_info = self.rfid_service.search_item(rfid)
                if item_info and item_info.get('status') == 'не_оплачен':
                    unpaid_items.append({'rfid': rfid, 'name': item_info.get('name', 'Неизвестный товар')})
                elif not item_info:
                    unpaid_items.append({'rfid': rfid, 'name': 'Неизвестный товар (не в БД)'})

            if unpaid_items:
                self.alarm_count += 1
                self._trigger_alarm(unpaid_items)
            else:
                logger.info("Все товары оплачены или просрочены")

        except Exception as e:
            logger.error(f"Ошибка обработки сканирования: {e}")

    def run_continuous_mode(self) -> None:
        """Непрерывный режим работы магазина"""
        logger.info("=" * 60)
        logger.info("НЕПРЕРЫВНЫЙ РЕЖИМ РАБОТЫ МАГАЗИНА")
        logger.info("=" * 60)
        logger.info("Система работает. Нажмите Ctrl+C для остановки.\n")

        self.running = True
        last_daily_check = datetime.now()

        try:
            while self.running:
                self.process_antenna_reading()

                current_time = datetime.now()
                if (current_time.hour == self.daily_check_hour and
                        current_time.date() != last_daily_check.date()):
                    logger.info("\n" + "=" * 40)
                    logger.info("ЕЖЕДНЕВНАЯ ПРОВЕРКА ПРОСРОЧКИ")
                    logger.info("=" * 40)
                    expired = self.rfid_service.check_expired_items()
                    if expired:
                        logger.info(f"Найдено просроченных товаров: {len(expired)}")
                    else:
                        logger.info("Просроченных товаров не найдено")
                    last_daily_check = current_time
                    logger.info("=" * 40 + "\n")

                if self.scan_count % 20 == 0:
                    self.show_mini_stats()

                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            logger.info("Остановка непрерывного режима...")
            self.running = False
            self.reader.disconnect()
        except Exception as e:
            logger.info(f"Критическая ошибка: {e}")
            self.running = False
            self.reader.disconnect()

    def show_settings_menu(self) -> None:
        """Меню настроек системы (исправлено)"""
        logger.info("=" * 60)
        logger.info("НАСТРОЙКИ СИСТЕМЫ")
        logger.info("=" * 60)

        logger.info(f"Текущие настройки:")
        logger.info(f"Интервал сканирования: {self.check_interval} сек")
        logger.info(f"Час ежедневной проверки: {self.daily_check_hour}:00")
        logger.info(f"Интервал проверки запасов: {self.hourly_check_interval} часов")
        logger.info(f"Telegram бот: {'Включен' if self.tg_bot else 'Выключен'}")

        logger.info("Настройки:")
        logger.info("1. Изменить интервал сканирования")
        logger.info("2. Изменить час ежедневной проверки")
        logger.info("3. Изменить интервал проверки запасов")
        logger.info("0. Назад")

        try:
            choice = input("\nВыберите действие (0-3): ").strip()

            if choice == "0":
                return
            elif choice == "1":
                try:
                    new_interval = int(input("Новый интервал (секунды, 1-30): "))
                    if 1 <= new_interval <= 30:
                        self.check_interval = new_interval
                        logger.info(f"Интервал изменен на {new_interval} секунд")
                    else:
                        logger.info("Интервал должен быть от 1 до 30 секунд")
                except ValueError:
                    logger.info("Введите число")
            elif choice == "2":
                try:
                    new_hour = int(input("Новый час (0-23): "))
                    if 0 <= new_hour <= 23:
                        self.daily_check_hour = new_hour
                        logger.info(f"Час ежедневной проверки изменен на {new_hour}:00")
                    else:
                        logger.info("Час должен быть от 0 до 23")
                except ValueError:
                    logger.info("Введите число")
            elif choice == "3":
                try:
                    new_interval = int(input("Новый интервал (часы, 1-24): "))
                    if 1 <= new_interval <= 24:
                        self.hourly_check_interval = new_interval
                        logger.info(f"Интервал проверки запасов изменен на {new_interval} часов")
                    else:
                        logger.info("Интервал должен быть от 1 до 24 часов")
                except ValueError:
                    logger.info("Введите число")
        except KeyboardInterrupt:
            logger.info("Возврат в главное меню...")
        except Exception as e:
            logger.info(f"Ошибка в настройках: {e}")


    def run_demo_mode(self) -> None:
        """Демонстрационный режим с разными сценариями"""
        logger.info("=" * 60)
        logger.info("ДЕМО-РЕЖИМ: СЦЕНАРИИ РАБОТЫ МАГАЗИНА")
        logger.info("=" * 60)

        scenarios = {
            "1": {"name": "Покупатель с неоплаченными товарами", "tags": ["RFID_7E3A5B1C", "RFID_8F4B6C2D"]},
            "2": {"name": "Покупатель с оплаченными товарами", "tags": ["RFID_ABCD1234", "RFID_EFGH5678"]},
            "3": {"name": "Смешанный случай", "tags": ["RFID_7E3A5B1C", "RFID_ABCD1234"]},
            "4": {"name": "Один неоплаченный товар", "tags": ["RFID_9A5C7D3E"]},
            "5": {"name": "Пустая корзина", "tags": []},
            "6": {"name": "Товар с истекающим сроком", "tags": ["RFID_7E3A5B1C"]},
            "7": {"name": "Товар с низким остатком", "tags": ["RFID_9A5C7D3E"]},
        }

        while True:
            logger.info("Доступные сценарии:")
            for key, scenario in scenarios.items():
                logger.info(f"   {key}. {scenario['name']}")
            logger.info("0. Выход в главное меню")

            try:
                choice = input("\nВыберите сценарий (0-7): ").strip()

                if choice == "0":
                    logger.info("Возврат в главное меню...")
                    break

                elif choice in scenarios:
                    scenario = scenarios[choice]
                    logger.info(f"Запуск сценария: {scenario['name']}")
                    logger.info(f"RFID метки: {scenario['tags']}")

                    # Обрабатываем метки
                    should_alarm = self.rfid_service.process_detected_tags(scenario['tags'])

                    if should_alarm:
                        logger.info("СЦЕНАРИЙ: Вызываем охрану!")
                    else:
                        logger.info("СЦЕНАРИЙ: Покупатель может пройти")

                    # Если это сценарий 3, демонстрируем процесс оплаты
                    if choice == "3":
                        input("\nНажмите Enter для имитации оплаты неоплаченного товара...")

                        # Оплачиваем неоплаченный товар
                        self.rfid_service.mark_as_paid(["RFID_7E3A5B1C"], "demo_cashier")

                        logger.info("Повторное сканирование после оплаты...")
                        should_alarm = self.rfid_service.process_detected_tags(scenario['tags'])

                        if should_alarm:
                            logger.info("ОШИБКА: Тревога всё ещё активна!")
                        else:
                            logger.info("Всё в порядке, тревоги нет")

                    input("\nНажмите Enter для продолжения...")

                else:
                    logger.info("Неверный выбор. Попробуйте снова.")

            except KeyboardInterrupt:
                logger.info("Возврат в главное меню...")
                break

    def show_system_stats(self) -> None:
        """Показать подробную статистику системы"""
        logger.info("=" * 60)
        logger.info("ПОДРОБНАЯ СТАТИСТИКА СИСТЕМЫ")
        logger.info("=" * 60)

        try:
            stats = self.rfid_service.get_system_stats()

            logger.info(f"ТОВАРЫ:")
            logger.info(f"Всего товаров в базе: {stats.get('total_items', 0)}")
            logger.info(f"Не оплачено: {stats.get('not_paid_items', 0)}")
            logger.info(f"Оплачено: {stats.get('paid_items', 0)}")
            logger.info(f"Просрочено: {stats.get('expired_items', 0)}")

            logger.info(f"ТРЕВОГИ:")
            active_alarms = self.rfid_service.alarm_manager.get_active_alarms()
            logger.info(f"Активных тревог: {len(active_alarms)}")

            if active_alarms:
                logger.info(f"Последние активные тревоги:")
                for alarm in active_alarms[:3]:
                    logger.info(f"{alarm.item_name} (RFID: {alarm.rfid_uid})")

            logger.info(f"СИСТЕМА:")
            logger.info(f"Всего сканирований: {self.scan_count}")
            logger.info(f"Всего тревог: {self.alarm_count}")
            logger.info(f"Telegram бот: {'Активен' if self.tg_bot else 'Не активен'}")
            logger.info(f"Интервал сканирования: {self.check_interval} сек")
            logger.info(f"Ежедневная проверка: {self.daily_check_hour}:00")


        except Exception as e:
            logger.info(f"Ошибка получения статистики: {e}")

    def show_mini_stats(self) -> None:
        """Показать мини-статистику"""
        stats = self.rfid_service.get_system_stats()

        logger.info("=" * 40)
        logger.info("ИНИ-СТАТИСТИКА")
        logger.info("=" * 40)
        logger.info(f"Сканирований: {self.scan_count} | Тревог: {self.alarm_count}")
        logger.info(f"Товаров: {stats.get('total_items', 0)} | Не оплачено: {stats.get('not_paid_items', 0)}")
        logger.info(f"Telegram бот: {'Y' if self.tg_bot else 'N'}")
        logger.info("=" * 40)

    def search_item_menu(self) -> None:
        """Меню поиска товара по RFID"""
        logger.info("=" * 60)
        logger.info("ПОИСК ТОВАРА ПО RFID МЕТКЕ")
        logger.info("=" * 60)

        while True:
            try:
                rfid_input = input("\nВведите RFID метку (или '0' для выхода): ").strip()

                if rfid_input == "0":
                    logger.info("Возврат в главное меню...")
                    break

                if not rfid_input:
                    logger.info("Введите RFID метку")
                    continue

                # Ищем товар
                item_info = self.rfid_service.search_item(rfid_input)

                if not item_info:
                    logger.info(f"Товар с RFID '{rfid_input}' не найден")
                    continue

                # Выводим информацию о товаре
                logger.info("=" * 40)
                logger.info("ТОВАР НАЙДЕН")
                logger.info("=" * 40)
                logger.info(f"Название: {item_info['name']}")
                logger.info(f"RFID: {item_info['rfid_uid']}")
                logger.info(f"Статус: {item_info['status']}")

                if item_info['expiration_date']:
                    exp_date = datetime.fromisoformat(item_info['expiration_date']).strftime('%d.%m.%Y')
                    logger.info(f"Срок годности: {exp_date}")

                if item_info['last_seen']:
                    last_seen = datetime.fromisoformat(item_info['last_seen']).strftime('%d.%m.%Y %H:%M:%S')
                    logger.info(f"Последнее сканирование: {last_seen}")

                # История
                if item_info['history']:
                    logger.info(f"ИСТОРИЯ ИЗМЕНЕНИЙ:")
                    for h in item_info['history']:
                        time_str = datetime.fromisoformat(h['time']).strftime('%H:%M:%S')
                        logger.info(f"{time_str}: {h['old_status'] or '?'} → {h['new_status']} ({h['source']})")

                logger.info("=" * 40)

            except KeyboardInterrupt:
                logger.info("Возврат в главное меню...")
                break
            except Exception as e:
                logger.info(f"Ошибка поиска: {e}")

    def telegram_bot_menu(self) -> None:
        """Меню управления Telegram ботом"""
        if not self.tg_bot:
            logger.info("Telegram бот не инициализирован!")
            logger.info("Проверьте токен бота в main.py")
            return

        logger.info("=" * 60)
        logger.info("УПРАВЛЕНИЕ TELEGRAM БОТОМ")
        logger.info("=" * 60)

        logger.info(f"Статус бота: {'Активен' if self.tg_bot else 'Не активен'}")

        logger.info("Инструкция:")
        logger.info("1. Найдите бота в Telegram по имени, которое вы указали в @BotFather")
        logger.info("2. Напишите боту команду /start")
        logger.info("3. Используйте кнопки или команды для управления")

        logger.info("Основные команды:")
        logger.info("   /start - начало работы с ботом")
        logger.info("   /status - статус системы")
        logger.info("   /stock - показать запасы товаров")
        logger.info("   /quick - быстрые действия")
        logger.info("   /alarms - последние тревоги")
        logger.info("   /find - поиск товара по RFID")
        logger.info("   /help - справка по командам")

        logger.info("Уведомления:")
        logger.info("Бот автоматически отправляет уведомления о:")
        logger.info("Попытках выноса неоплаченных товаров")
        logger.info("Товарах с истекающим сроком годности")
        logger.info("Низких остатках товаров")
        logger.info("Просроченных товарах")

        logger.info("=" * 60)

    def show_main_menu(self) -> None:
        """Показать главное меню"""
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

    def inventory_management_menu(self) -> None:
        """Меню управления запасами"""
        logger.info("=" * 60)
        logger.info("УПРАВЛЕНИЕ ЗАПАСАМИ ТОВАРОВ")
        logger.info("=" * 60)

        while True:
            logger.info("Доступные действия:")
            logger.info("1. Показать все товары")
            logger.info("2. Обновить количество товара")
            logger.info("3. Добавить новый товар")
            logger.info("4. Проверить пороги (отправить уведомления)")
            logger.info("5. Проверить сроки годности")
            logger.info("6. Проверить просроченные товары")
            logger.info("0. Назад в главное меню")

            try:
                choice = input("\nВыберите действие (0-6): ").strip()

                if choice == "0":
                    logger.info("Возврат в главное меню...")
                    break

                elif choice == "1":
                    products = inventory_service.get_all_products()

                    if not products:
                        logger.info("Товаров не найдено")
                        continue

                    logger.info("=" * 60)
                    logger.info("СПИСОК ТОВАРОВ")
                    logger.info("=" * 60)

                    for product in products:
                        status_icon = ""
                        if product["status"] == "critical":
                            status_icon = "🚨"
                        elif product["status"] == "warning":
                            status_icon = "⚠️"
                        else:
                            status_icon = "✅"

                        logger.info(f"{status_icon} {product['name']} ({product['sku']})")
                        logger.info(f"Количество: {product['current_quantity']} {product['unit']}")
                        logger.info(f"Пороги: {product['min_threshold']}/{product['critical_threshold']}")
                        logger.info(f"Целевой запас: {product['target_quantity']}")

                    logger.info("=" * 60)

                elif choice == "2":
                    sku = input("Введите артикул товара: ").strip()
                    try:
                        new_quantity = int(input("Введите новое количество: ").strip())

                        alerts = inventory_service.update_quantity(sku, new_quantity)

                        if alerts:
                            logger.info("ОПОВЕЩЕНИЯ:")
                            for alert in alerts:
                                logger.info(f"{alert.message}")

                        logger.info(f"Количество товара обновлено")

                    except ValueError:
                        logger.info("Ошибка: количество должно быть числом")
                    except Exception as e:
                        logger.info(f"Ошибка: {e}")

                elif choice == "3":
                    try:
                        sku = input("Артикул: ").strip()
                        name = input("Название: ").strip()
                        current_quantity = int(input("Текущее количество: ").strip())
                        min_threshold = int(input("Порог 'пора заказывать': ").strip())
                        critical_threshold = int(input("Критический порог: ").strip())
                        target_quantity = int(input("Целевой запас: ").strip())

                        success = inventory_service.add_product(
                            sku=sku,
                            name=name,
                            current_quantity=current_quantity,
                            min_threshold=min_threshold,
                            critical_threshold=critical_threshold,
                            target_quantity=target_quantity
                        )

                        if success:
                            logger.info(f"Товар '{name}' добавлен")
                        else:
                            logger.info("Ошибка добавления товара")

                    except ValueError:
                        logger.info("Ошибка: все числовые значения должны быть целыми числами")
                    except Exception as e:
                        logger.info(f"Ошибка: {e}")

                elif choice == "4":
                    alerts = inventory_service.check_all_products()

                    if alerts:
                        logger.info("НАЙДЕНЫ ПРОБЛЕМЫ С ЗАПАСАМИ:")
                        for alert in alerts:
                            logger.info(f"{alert.message}")
                    else:
                        logger.info("Все товары в норме")

                elif choice == "5":
                    logger.info("Проверка товаров с истекающим сроком годности...")
                    expiring_items = self.rfid_service.check_expiring_soon()

                    if expiring_items:
                        logger.info(f"Найдено {len(expiring_items)} товаров:")
                        for item in expiring_items:
                            logger.info(f"{item['name']}: {item['days_left']} дней до истечения")
                    else:
                        logger.info("Нет товаров с истекающим сроком годности")

                elif choice == "6":
                    logger.info("Проверка просроченных товаров...")
                    expired = self.rfid_service.check_expired_items()

                    if expired:
                        logger.info(f"Найдено {len(expired)} просроченных товаров")
                        for rfid in expired[:5]:
                            item = self.rfid_service.search_item(rfid)
                            if item:
                                logger.info(f"{item['name']} (RFID: {rfid})")
                    else:
                        logger.info("Нет просроченных товаров")

                else:
                    logger.info("Неверный выбор")

            except KeyboardInterrupt:
                logger.info("Возврат в главное меню...")
                break

    def run(self) -> None:
        """Главный цикл программы"""
        try:
            while True:
                self.show_main_menu()

                try:
                    choice = input("\nВыберите действие (0-7): ").strip()

                    if choice == "0":
                        logger.info("Завершение работы системы...")
                        if self.tg_bot:
                            logger.info("Остановка Telegram бота...")
                        logger.info("До свидания!")
                        break

                    elif choice == "1":
                        self.run_continuous_mode()

                    elif choice == "2":
                        self.run_demo_mode()

                    elif choice == "3":
                        self.show_system_stats()
                        input("\nНажмите Enter для продолжения...")

                    elif choice == "4":
                        self.search_item_menu()

                    elif choice == "5":
                        self.inventory_management_menu()

                    elif choice == "6":
                        self.telegram_bot_menu()
                        input("\nНажмите Enter для продолжения...")

                    elif choice == "7":
                        self.show_settings_menu()

                    else:
                        logger.info("Неверный выбор. Попробуйте снова.")

                except KeyboardInterrupt:
                    logger.info("Прервано пользователем")
                    continue

        except KeyboardInterrupt:
            logger.info("Завершение работы системы...")
        except Exception as e:
            logger.info(f"Критическая ошибка: {e}")


def main():
    logger.info("=" * 60)
    logger.info("ЗАПУСК RFID СИСТЕМЫ С TELEGRAM БОТОМ")
    logger.info("=" * 60)

    system = RFIDStoreSystem()
    if not system.initialize():
        logger.info("Не удалось инициализировать систему")
        sys.exit(1)

    system.run()


if __name__ == "__main__":
    main()