import logging
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

logger = logging.getLogger(__name__)


class RFIDTelegramBot:
    """Telegram бот для мониторинга RFID-системы магазина с управлением запасами"""

    def __init__(self, token: str, admin_chat_ids: List[int] = None, inventory_service=None, rfid_service=None):
        self.token = token
        self.admin_chat_ids = admin_chat_ids or []
        self.inventory_service = inventory_service
        self.rfid_service = rfid_service
        self.application = None
        self.chat_ids = set()
        self.loop = None
        self.WAITING_FOR_RFID = 1

    async def start(self):
        """Запуск бота"""
        try:
            self.application = Application.builder().token(self.token).build()
            self._register_handlers()
            logger.info("Запуск Telegram бота...")
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            logger.info("Telegram бот запущен и готов к работе!")
        except Exception as e:
            logger.error(f"Ошибка запуска Telegram бота: {e}")
            raise

    def _register_handlers(self):
        """Регистрация обработчиков команд"""
        # Основные команды
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("alarms", self.alarms_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("help", self.help_command))

        # Команды для управления запасами
        self.application.add_handler(CommandHandler("stock", self.inventory_status_command))
        self.application.add_handler(CommandHandler("check_stock", self.check_stock_command))
        self.application.add_handler(CommandHandler("quick", self.quick_actions_command))
        self.application.add_handler(CommandHandler("update_product", self.update_product_command))
        self.application.add_handler(CommandHandler("products", self.products_list_command))

        # Команда поиска по категориям (бывший find)
        self.application.add_handler(CommandHandler("find", self.category_search_command))

        # Обработчик кнопок клавиатуры
        self.application.add_handler(MessageHandler(
            filters.Regex(r'^(🚨 Статус|📊 Статистика|🔍 Поиск|📝 История|📦 Запасы|🚨 Проверить пороги|📦 Список товаров|⚡ Быстрые действия|🔄 Обновить всё|🆘 Помощь)$'),
            self.button_handler
        ))

        # Обработчик inline-кнопок
        self.application.add_handler(CallbackQueryHandler(self.button_callback))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        chat_id = update.effective_chat.id

        self.chat_ids.add(chat_id)

        if self.admin_chat_ids and chat_id not in self.admin_chat_ids:
            await update.message.reply_text(
                "У вас нет доступа к этому боту.\n"
                "Обратитесь к администратору магазина."
            )
            return

        # Клавиатура с кнопками (добавлены новые)
        keyboard = [
            [KeyboardButton("🚨 Статус"), KeyboardButton("📊 Статистика")],
            [KeyboardButton("🔍 Поиск"), KeyboardButton("📝 История")],
            [KeyboardButton("📦 Запасы"), KeyboardButton("🚨 Проверить пороги")],
            [KeyboardButton("📦 Список товаров"), KeyboardButton("⚡ Быстрые действия")],
            [KeyboardButton("🔄 Обновить всё"), KeyboardButton("🆘 Помощь")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        welcome_text = (
            "🛒 СИСТЕМА УПРАВЛЕНИЯ МАГАЗИНОМ 24/7!\n\n"
            "Я буду уведомлять вас о событиях в магазине:\n"
            "• 🚨 Тревоги при попытке выноса товара\n"
            "• 📊 Статистика продаж и товаров\n"
            "• 📦 Управление запасами товаров\n"
            "• 🔍 Поиск товаров по категориям\n"
            "• 📝 История событий и тревог\n\n"
            "Основные команды:\n"
            "/status - текущий статус системы\n"
            "/stock - показать запасы (требующие пополнения и просрочку)\n"
            "/check_stock - проверить пороги и отправить уведомления\n"
            "/quick - быстрые действия\n"
            "/alarms - последние тревоги\n"
            "/find - поиск товара по категориям\n"
            "/help - справка по командам\n\n"
            "Используйте кнопки ниже для быстрого доступа!"
        )

        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
        logger.info(f"Новый пользователь: {user.full_name} (ID: {chat_id})")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать текущий статус системы (активные тревоги, общая статистика)"""
        try:
            stats = self.rfid_service.get_system_stats()
            active_alarms = self.rfid_service.alarm_manager.get_active_alarms()

            text = (
                f"🚨 ТЕКУЩИЙ СТАТУС СИСТЕМЫ\n"
                f"{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
                f"• Всего товаров: {stats.get('total_items', 0)}\n"
                f"• Не оплачено: {stats.get('not_paid_items', 0)}\n"
                f"• Оплачено: {stats.get('paid_items', 0)}\n"
                f"• Просрочено: {stats.get('expired_items', 0)}\n"
                f"• Активных тревог: {len(active_alarms)}\n"
            )

            if active_alarms:
                text += "\n⚠️ *Активные тревоги:*\n"
                for alarm in active_alarms[:5]:
                    text += f"• {alarm.item_name} (RFID: {alarm.rfid_uid[:8]}...)\n"

            await update.message.reply_text(text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Ошибка status_command: {e}")
            await update.message.reply_text("Ошибка получения статуса системы.")

    async def alarms_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать историю тревог"""
        try:
            history = self.rfid_service.alarm_manager.get_alarm_history(limit=10)
            if not history:
                await update.message.reply_text("История тревог пуста.")
                return

            text = "📝 ИСТОРИЯ ТРЕВОГ (последние 10)\n\n"
            for alarm in history:
                status = "✅" if alarm.resolved else "🚨"
                time_str = alarm.timestamp.strftime('%d.%m %H:%M')
                text += f"{status} {alarm.item_name} – {time_str}\n"
                if alarm.resolved and alarm.resolved_by:
                    text += f"   Решено: {alarm.resolved_by}\n"
            await update.message.reply_text(text)
        except Exception as e:
            logger.error(f"Ошибка alarms_command: {e}")
            await update.message.reply_text("Ошибка получения истории тревог.")

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статистику (без последних событий)"""
        try:
            stats = self.rfid_service.get_system_stats()
            active_alarms = self.rfid_service.alarm_manager.get_active_alarms()

            text = (
                f"📊 СТАТИСТИКА СИСТЕМЫ\n"
                f"{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
                f"• Всего товаров: {stats.get('total_items', 0)}\n"
                f"• Не оплачено: {stats.get('not_paid_items', 0)}\n"
                f"• Оплачено: {stats.get('paid_items', 0)}\n"
                f"• Просрочено: {stats.get('expired_items', 0)}\n"
                f"• Активных тревог: {len(active_alarms)}\n"
            )

            if active_alarms:
                text += "\n⚠️ Активные тревоги:\n"
                for alarm in active_alarms[:3]:
                    text += f"• {alarm.item_name}\n"

            await update.message.reply_text(text)
        except Exception as e:
            logger.error(f"Ошибка stats_command: {e}")
            await update.message.reply_text("Ошибка получения статистики.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать справку"""
        help_text = (
            "🆘 *СПРАВКА ПО КОМАНДАМ*\n\n"
            "*/start* – Начать работу с ботом\n"
            "*/status* – Текущий статус системы\n"
            "*/stock* – Показать запасы (требующие пополнения и просрочку)\n"
            "*/check_stock* – Проверить пороги и отправить уведомления\n"
            "*/quick* – Быстрые действия (кнопки)\n"
            "*/products* – Список всех товаров\n"
            "*/update_product* АРТИКУЛ КОЛ-ВО – Обновить количество товара\n"
            "*/alarms* – История тревог\n"
            "*/stats* – Подробная статистика\n"
            "*/find* – Поиск товара по категориям\n"
            "*/help* – Эта справка\n\n"
            "Кнопки клавиатуры дублируют основные команды."
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def inventory_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать только товары, требующие пополнения, и просроченные"""
        try:
            products = self.inventory_service.get_all_products()
            low_stock = [p for p in products if p['status'] in ('warning', 'critical')]
            expired_items = self.rfid_service.get_expired_items_info()

            message = "📦 *СОСТОЯНИЕ ЗАПАСОВ*\n\n"

            if low_stock:
                message += "*🔻 ТРЕБУЮТ ПОПОЛНЕНИЯ:*\n"
                for p in low_stock:
                    icon = "🚨" if p['status'] == 'critical' else "⚠️"
                    message += f"{icon} {p['name']} – осталось {p['current_quantity']} {p['unit']} (порог {p['min_threshold']})\n"
                message += "\n"
            else:
                message += "✅ Все товары в достатке.\n\n"

            if expired_items:
                message += "*🗑️ ПРОСРОЧЕННЫЕ ТОВАРЫ:*\n"
                for item in expired_items:
                    message += f"• {item['name']} (годен до {item['expiration_date']})\n"
            else:
                message += "✅ Просроченных товаров нет."

            await update.message.reply_text(message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Ошибка inventory_status_command: {e}")
            await update.message.reply_text("Ошибка получения информации о запасах.")

    async def check_stock_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Проверить запасы и отправить уведомления"""
        try:
            alerts = self.inventory_service.check_all_products()
            if not alerts:
                await update.message.reply_text("✅ Все товары в норме.")
                return

            message = "🚨 ОБНАРУЖЕНЫ ПРОБЛЕМЫ С ЗАПАСАМИ\n\n"
            for alert in alerts:
                icon = "🚨" if alert.alert_level == "critical" else "⚠️"
                message += f"{icon} {alert.message}\n"

            await update.message.reply_text(message)
            await self.send_message_to_all(message)
        except Exception as e:
            logger.error(f"Ошибка check_stock_command: {e}")
            await update.message.reply_text("Ошибка проверки запасов.")

    async def quick_actions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Быстрые действия - inline-кнопки"""
        keyboard = [
            [InlineKeyboardButton("📊 Статус запасов", callback_data="quick_inventory"),
             InlineKeyboardButton("🚨 Проверить критические", callback_data="quick_critical")],
            [InlineKeyboardButton("📦 Список товаров", callback_data="quick_products"),
             InlineKeyboardButton("🔄 Обновить все", callback_data="quick_refresh")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("⚡ БЫСТРЫЕ ДЕЙСТВИЯ\n\nВыберите действие:", reply_markup=reply_markup)

    async def update_product_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обновить количество товара"""
        if len(context.args) < 2:
            await update.message.reply_text(
                "Использование:\n/update_product АРТИКУЛ КОЛИЧЕСТВО\nПример:\n/update_product MILK001 25"
            )
            return
        sku = context.args[0]
        try:
            quantity = int(context.args[1])
            alerts = self.inventory_service.update_quantity(sku, quantity)
            if alerts:
                msg = f"✅ Товар обновлен\n\nОповещения:\n" + "\n".join(a.message for a in alerts)
            else:
                msg = f"✅ Товар {sku} обновлен: {quantity} шт."
            await update.message.reply_text(msg)
        except ValueError:
            await update.message.reply_text("❌ Количество должно быть числом")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

    async def products_list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список всех товаров"""
        try:
            products = self.inventory_service.get_all_products()
            if not products:
                await update.message.reply_text("📦 Список товаров пуст.")
                return
            message = "📦 *СПИСОК ТОВАРОВ*\n\n"
            for p in products[:10]:
                icon = "✅"
                if p['status'] == 'critical':
                    icon = "🚨"
                elif p['status'] == 'warning':
                    icon = "⚠️"
                message += f"{icon} *{p['name']}*\n"
                message += f"   Артикул: {p['sku']}, Остаток: {p['current_quantity']} {p['unit']}\n"
            if len(products) > 10:
                message += f"\n... и еще {len(products) - 10} товаров."
            await update.message.reply_text(message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Ошибка products_list_command: {e}")
            await update.message.reply_text("Ошибка получения списка товаров.")

    async def category_search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Поиск по категориям (вместо поиска по RFID)"""
        try:
            categories = self.rfid_service.get_all_categories()
            if not categories:
                await update.message.reply_text("Категории товаров не найдены.")
                return

            keyboard = []
            row = []
            for i, cat in enumerate(categories):
                button = InlineKeyboardButton(cat, callback_data=f"cat_{cat}")
                row.append(button)
                if (i+1) % 2 == 0:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Выберите категорию товаров:", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка category_search_command: {e}")
            await update.message.reply_text("Ошибка получения категорий.")

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопки клавиатуры"""
        text = update.message.text
        if text == "🚨 Статус":
            await self.status_command(update, context)
        elif text == "📊 Статистика":
            await self.stats_command(update, context)
        elif text == "🔍 Поиск":
            await self.category_search_command(update, context)
        elif text == "📝 История":
            await self.alarms_command(update, context)
        elif text == "📦 Запасы":
            await self.inventory_status_command(update, context)
        elif text == "🚨 Проверить пороги":
            await self.check_stock_command(update, context)
        elif text == "📦 Список товаров":
            await self.products_list_command(update, context)
        elif text == "⚡ Быстрые действия":
            await self.quick_actions_command(update, context)
        elif text == "🔄 Обновить всё":
            await self.inventory_status_command(update, context)
        elif text == "🆘 Помощь":
            await self.help_command(update, context)

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик inline-кнопок"""
        query = update.callback_query
        await query.answer()

        data = query.data

        if data.startswith("cat_"):
            category = data[4:]
            items = self.rfid_service.get_items_by_category(category)
            if not items:
                await query.edit_message_text(f"В категории '{category}' товаров нет.")
                return

            text = f"*Товары в категории {category}:*\n\n"
            for item in items:
                status_emoji = {
                    "не_оплачен": "🚨",
                    "оплачен": "✅",
                    "просрочен": "⚠️"
                }.get(item['status'], "❓")
                exp = f" (годен до {item['expiration_date']})" if item.get('expiration_date') else ""
                text += f"{status_emoji} {item['name']}{exp}\n"
            await query.edit_message_text(text, parse_mode='Markdown')

        elif data.startswith("resolve_"):
            rfid_uid = data[8:]
            user_name = query.from_user.full_name or "Сотрудник"
            success = self.rfid_service.resolve_alarm(rfid_uid, user_name)
            if success:
                await query.edit_message_text(f"✅ Тревога для {rfid_uid} разрешена.")
            else:
                await query.edit_message_text(f"❌ Не удалось разрешить тревогу.")

        elif data == "quick_inventory":
            await self.inventory_status_command(update, context)
        elif data == "quick_critical":
            alerts = self.inventory_service.check_all_products()
            critical = [a for a in alerts if a.alert_level == "critical"]
            if critical:
                msg = "🚨 КРИТИЧЕСКИЕ ТОВАРЫ:\n\n" + "\n".join(a.message for a in critical)
            else:
                msg = "✅ Нет критически низких запасов."
            await query.edit_message_text(msg)
        elif data == "quick_products":
            await self.products_list_command(update, context)
        elif data == "quick_refresh":
            await query.edit_message_text("🔄 Обновление...")
            await self.inventory_status_command(update, context)

    async def send_alarm_notification(self, rfid_uid: str, item_name: str):
        """Отправка уведомления о тревоге всем подключённым пользователям"""
        if not self.application:
            return

        alarm_message = (
            f"🚨 ТРЕВОГА В МАГАЗИНЕ!\n\n"
            f"Товар: {item_name}\n"
            f"RFID: {rfid_uid}\n"
            f"Время: {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"Товар попытались вынести без оплаты!"
        )

        keyboard = [[InlineKeyboardButton("✅ Разрешить тревогу", callback_data=f"resolve_{rfid_uid}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        for chat_id in self.chat_ids:
            try:
                await self.application.bot.send_message(chat_id=chat_id, text=alarm_message, reply_markup=reply_markup)
            except Exception as e:
                logger.debug(f"Не удалось отправить уведомление в чат {chat_id}: {e}")

    async def send_message_to_all(self, message: str):
        """Отправка сообщения всем подключённым пользователям"""
        if not self.application or not self.chat_ids:
            return
        for chat_id in self.chat_ids:
            try:
                await self.application.bot.send_message(chat_id=chat_id, text=message)
            except Exception as e:
                logger.debug(f"Не удалось отправить сообщение в чат {chat_id}: {e}")

    async def stop(self):
        """Остановка бота"""
        if self.application:
            await self.application.stop()