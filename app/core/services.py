import logging
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from dataclasses import dataclass

from app.core.database import db
from app.core.models import TaggedItem, ItemHistory, ItemStatus, CatalogProduct

logger = logging.getLogger(__name__)


@dataclass
class AlarmEvent:
    rfid_uid: str
    item_name: str
    timestamp: datetime
    resolved: bool = False
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None



class AlarmManager:
    """Менеджер тревог"""

    def __init__(self):
        self.active_alarms: Dict[str, AlarmEvent] = {}
        self.alarm_history: List[AlarmEvent] = []

    def add_alarm(self, rfid_uid: str, item_name: str) -> AlarmEvent:
        """Добавить новую тревогу"""
        alarm = AlarmEvent(
            rfid_uid=rfid_uid,
            item_name=item_name,
            timestamp=datetime.now()
        )

        # Если уже есть активная тревога для этого RFID - обновляем время
        if rfid_uid in self.active_alarms:
            self.active_alarms[rfid_uid].timestamp = datetime.now()
            return self.active_alarms[rfid_uid]

        self.active_alarms[rfid_uid] = alarm
        self.alarm_history.append(alarm)

        logger.warning(f"НОВАЯ ТРЕВОГА: {item_name} (RFID: {rfid_uid})")
        return alarm

    def resolve_alarm(self, rfid_uid: str, resolved_by: str) -> bool:
        """Разрешить тревогу"""
        if rfid_uid in self.active_alarms:
            alarm = self.active_alarms[rfid_uid]
            alarm.resolved = True
            alarm.resolved_by = resolved_by
            alarm.resolved_at = datetime.now()

            del self.active_alarms[rfid_uid]
            logger.info(f"Тревога разрешена: {rfid_uid} (сотрудник: {resolved_by})")
            return True
        return False

    def get_active_alarms(self) -> List[AlarmEvent]:
        """Получить список активных тревог"""
        return list(self.active_alarms.values())

    def get_alarm_history(self, limit: int = 10) -> List[AlarmEvent]:
        """Получить историю тревог"""
        return sorted(
            self.alarm_history,
            key=lambda x: x.timestamp,
            reverse=True
        )[:limit]


class RFIDService:
    def __init__(self, db, alarm_manager=None, telegram_bot=None):
        self.db = db
        self.alarm_manager = alarm_manager or AlarmManager()
        self.telegram_bot = telegram_bot
        self.last_check_time = datetime.now()
        self.inventory_service = None

    async def send_telegram_notification(self, message: str, notification_type: str = "info"):
        """Отправить уведомление в Telegram (использует глобальный бот и его loop)"""
        if not self.telegram_bot or not self.telegram_bot.loop:
            logger.warning("Telegram бот не передан")
            return False
        asyncio.run_coroutine_threadsafe(
            self._send_async(message, notification_type),
            self.telegram_bot.loop
        )
        return True

    async def _send_async(self, message: str, notification_type: str):
        """Асинхронная отправка (форматирование и вызов метода бота)"""
        if not self.telegram_bot:
            return

        emoji = {
            "alarm": "🚨",
            "expiration": "⚠️",
            "low_stock": "📉",
            "critical_stock": "🚨",
            "info": "ℹ️"
        }.get(notification_type, "ℹ️")

        formatted_message = f"{emoji} *УВЕДОМЛЕНИЕ: {notification_type.upper()}*\n\n{message}\n\n⏰ {datetime.now().strftime('%H:%M:%S')}"
        await self.telegram_bot.send_message_to_all(formatted_message)
        logger.info(f"Уведомление отправлено в Telegram: {notification_type}")


    def _send_notification_sync(self, message: str, notification_type: str = "info"):
        """Синхронная отправка уведомления через цикл бота"""
        if not self.telegram_bot or not self.telegram_bot.loop:
            logger.warning("Нет бота или цикла для отправки уведомления")
            return False
        asyncio.run_coroutine_threadsafe(
            self._send_async(message, notification_type),
            self.telegram_bot.loop
        )
        return True

    def get_all_categories(self) -> List[str]:
        """Получить все уникальные категории товаров"""
        try:
            with self.db.get_session() as session:
                categories = session.query(CatalogProduct.category).distinct().all()
                return [c[0] for c in categories if c[0]]
        except Exception as e:
            logger.error(f"Ошибка получения категорий: {e}")
            return []

    def get_items_by_category(self, category: str) -> List[Dict[str, Any]]:
        try:
            with self.db.get_session() as session:
                items = session.query(TaggedItem).join(CatalogProduct).filter(
                    CatalogProduct.category == category
                ).all()
                result = []
                for item in items:
                    result.append({
                        'name': item.product.name,
                        'rfid_uid': item.rfid_uid,
                        'status': item.status,
                        'expiration_date': item.expiration_date.strftime('%d.%m.%Y') if item.expiration_date else None,
                    })
                return result
        except Exception as e:
            logger.error(f"Ошибка получения товаров по категории {category}: {e}")
            return []

    def get_expired_items_info(self) -> List[Dict[str, Any]]:
        try:
            with self.db.get_session() as session:
                items = session.query(TaggedItem).join(CatalogProduct).filter(
                    TaggedItem.expiration_date < date.today(),
                    TaggedItem.status == ItemStatus.EXPIRED.value
                ).all()
                result = []
                for item in items:
                    result.append({
                        'name': item.product.name,
                        'rfid_uid': item.rfid_uid,
                        'expiration_date': item.expiration_date.strftime('%d.%m.%Y') if item.expiration_date else None,
                    })
                return result
        except Exception as e:
            logger.error(f"Ошибка получения просроченных товаров: {e}")
            return []

    def check_expired_items(self) -> List[str]:
        """Проверить просроченные товары и отправить уведомления (синхронная версия)"""
        expired_tags = []
        try:
            with self.db.get_session() as session:
                expired_items = session.query(TaggedItem).filter(
                    TaggedItem.expiration_date < date.today(),
                    TaggedItem.status != ItemStatus.EXPIRED.value
                ).all()

                for item in expired_items:
                    old_status = item.status
                    item.status = ItemStatus.EXPIRED.value
                    expired_tags.append(item.rfid_uid)

                    self._log_status_change(
                        session=session,
                        rfid_uid=item.rfid_uid,
                        old_status=old_status,
                        new_status=ItemStatus.EXPIRED.value,
                        change_source="expiry_check"
                    )

                    # Отправляем уведомление о каждом просроченном товаре
                    message = f"ТОВАР ПРОСРОЧЕН!\n{item.product.name} (RFID: {item.rfid_uid})\nДата истечения: {item.expiration_date}"
                    # Запускаем асинхронную отправку
                    self._send_notification_sync(self.send_telegram_notification(message, "expiration"))

                if expired_items:
                    logger.warning(f"Обновлено статусов просрочки: {len(expired_items)}")
                    summary = f"ОБНАРУЖЕНО {len(expired_items)} ПРОСРОЧЕННЫХ ТОВАРОВ!"
                    self._send_notification_sync(self.send_telegram_notification(summary, "expiration"))
        except Exception as e:
            logger.error(f"Ошибка проверки просрочки: {e}")

        return expired_tags

    def process_detected_tags(self, tag_ids: List[str]) -> bool:
        """
        Обрабатывает считанные метки.
        Возвращает True, если нужно включить тревогу.
        Теперь также проверяет срок годности и остатки.
        """
        if not tag_ids:
            return False

        try:
            with self.db.get_session() as session:
                # Ищем товары среди считанных
                items = session.query(TaggedItem).join(CatalogProduct).filter(
                    TaggedItem.rfid_uid.in_(tag_ids)
                ).all()

                if not items:
                    return False

                # 1. Проверяем неоплаченные товары для тревоги
                unpaid_items = [item for item in items if item.status == ItemStatus.NOT_PAID.value]

                # 2. Для всех найденных товаров проверяем дополнительные условия
                for item in items:
                    # Проверка срока годности
                    if item.expiration_date:
                        days_left = (item.expiration_date - date.today()).days
                        if 0 < days_left <= 3:
                            # Отправляем уведомление о скором истечении срока
                            message = f"Товар '{item.product.name}' (RFID: {item.rfid_uid}) скоро просрочится!\nОсталось: {days_left} дней"
                            self._send_notification_sync(message, "expiration")

                    # Проверка остатков через inventory_service
                    product = session.query(CatalogProduct).filter_by(rfid_uid=item.rfid_uid).first()
                    if product:
                        # Проверяем критические остатки
                        if product.current_quantity <= product.critical_threshold:
                            message = f"КРИТИЧЕСКИ МАЛО ТОВАРА!\n{product.name}: осталось {product.current_quantity} {product.unit}\nПорог: {product.critical_threshold} {product.unit}"
                            self.send_telegram_notification(message, "critical_stock")
                        # Проверяем низкие остатки
                        elif product.current_quantity <= product.min_threshold:
                            message = f"ЗАКАНЧИВАЕТСЯ ТОВАР!\n{product.name}: осталось {product.current_quantity} {product.unit}\nПорог заказа: {product.min_threshold} {product.unit}"
                            self.send_telegram_notification(message, "low_stock")

                    # Логируем событие
                    self._log_status_change(
                        session=session,
                        rfid_uid=item.rfid_uid,
                        old_status=item.status,
                        new_status=item.status,
                        change_source="antenna_scan"
                    )

                # Если есть хотя бы один неоплаченный товар - тревога
                should_alarm = len(unpaid_items) > 0

                if should_alarm:
                    for item in unpaid_items:
                        alarm_event = self.alarm_manager.add_alarm(
                            rfid_uid=item.rfid_uid,
                            item_name=item.product.name
                        )
                        # Отправляем тревогу в Telegram
                        alarm_message = f"ТРЕВОГА! Обнаружен неоплаченный товар:\n{item.product.name}\nRFID: {item.rfid_uid}"
                        self.send_telegram_notification(alarm_message, "alarm")

                    logger.warning(f"ТРЕВОГА! Обнаружено {len(unpaid_items)} неоплаченных товаров")
                else:
                    logger.info(f"Все товары оплачены или просрочены")

                return should_alarm

        except Exception as e:
            logger.error(f"Ошибка обработки меток: {e}")
            return False

    def _log_status_change(self, session, rfid_uid: str, old_status: str, new_status: str, change_source: str):
        """Логировать изменение статуса"""
        history = ItemHistory(
            rfid_uid=rfid_uid,
            old_status=old_status,
            new_status=new_status,
            change_source=change_source
        )
        session.add(history)

    def mark_as_paid(self, tag_ids: List[str], cashier: str = "system") -> None:
        """Помечает товары как оплаченные и обновляет остатки"""
        if not tag_ids:
            return

        try:
            with self.db.get_session() as session:
                # Находим товары
                items = session.query(TaggedItem).filter(
                    TaggedItem.rfid_uid.in_(tag_ids)
                ).all()

                for item in items:
                    old_status = item.status
                    item.status = ItemStatus.PAID.value

                    # Логируем изменение
                    self._log_status_change(
                        session=session,
                        rfid_uid=item.rfid_uid,
                        old_status=old_status,
                        new_status=ItemStatus.PAID.value,
                        change_source=f"cashier_{cashier}"
                    )

                    # Если была активная тревога - разрешаем её
                    if item.rfid_uid in self.alarm_manager.active_alarms:
                        self.alarm_manager.resolve_alarm(item.rfid_uid, cashier)

                    # Уменьшаем остаток в inventory
                    product = session.query(CatalogProduct).filter_by(rfid_uid=item.rfid_uid).first()
                    if product:
                        product.current_quantity = max(0, product.current_quantity - 1)
                        product.last_updated = datetime.now()

                        # Проверяем остатки после продажи
                        if product.current_quantity <= product.critical_threshold:
                            message = f"ПРОДАЖА: Критически мало товара!\n{product.name}: осталось {product.current_quantity} {product.unit}"
                            self._send_notification_sync(self.send_telegram_notification(message, "critical_stock"))
                        elif product.current_quantity <= product.min_threshold:
                            message = f"ПРОДАЖА: Заканчивается товар!\n{product.name}: осталось {product.current_quantity} {product.unit}"
                            self.send_telegram_notification(message, "low_stock")

                logger.info(f"Помечено как оплачено: {len(items)} товаров (кассир: {cashier})")

        except Exception as e:
            logger.error(f"Ошибка при отметке оплаты: {e}")

    def get_system_stats(self) -> Dict[str, Any]:
        """Получить статистику системы"""
        try:
            with self.db.get_session() as session:
                total = session.query(TaggedItem).count()
                not_paid = session.query(TaggedItem).filter_by(status=ItemStatus.NOT_PAID.value).count()
                paid = session.query(TaggedItem).filter_by(status=ItemStatus.PAID.value).count()
                expired = session.query(TaggedItem).filter_by(status=ItemStatus.EXPIRED.value).count()

                # Получаем последние 5 событий
                recent_events = session.query(ItemHistory).order_by(
                    ItemHistory.change_time.desc()
                ).limit(5).all()

                events_list = []
                #for event in recent_events:
                    #events_list.append({
                        #'rfid_uid': event.rfid_uid,
                        #'event': f"{event.old_status or '?'} → {event.new_status}",
                        #'time': event.change_time.isoformat()
                   #  })

                return {
                    'total_items': total,
                    'not_paid_items': not_paid,
                    'paid_items': paid,
                    'expired_items': expired,
                    'recent_events': events_list
                }
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {}

    def search_item(self, rfid_uid: str) -> Optional[Dict[str, Any]]:
        """Поиск товара по RFID"""
        try:
            with self.db.get_session() as session:
                item = session.query(TaggedItem).filter_by(rfid_uid=rfid_uid).first()
                if not item:
                    return None

                # Получаем историю изменений
                history = session.query(ItemHistory).filter_by(
                    rfid_uid=rfid_uid
                ).order_by(ItemHistory.change_time.desc()).all()

                history_list = []
                for h in history:
                    history_list.append({
                        'time': h.change_time.isoformat(),
                        'old_status': h.old_status,
                        'new_status': h.new_status,
                        'source': h.change_source
                    })

                return {
                    'name': item.product.name,
                    'rfid_uid': item.rfid_uid,
                    'status': item.status,
                    'expiration_date': item.expiration_date.isoformat() if item.expiration_date else None,
                    'last_seen': item.last_seen.isoformat() if item.last_seen else None,
                    'history': history_list
                }
        except Exception as e:
            logger.error(f"Ошибка поиска товара: {e}")
            return None

    def resolve_alarm(self, rfid_uid: str, resolved_by: str) -> bool:
        """Разрешить тревогу"""
        return self.alarm_manager.resolve_alarm(rfid_uid, resolved_by)

    def add_test_item(self, name: str, rfid_uid: str, days_to_expire: int = 30):
        """Добавить тестовый товар"""
        try:
            with self.db.get_session() as session:
                item = TaggedItem(
                    item_name=name,
                    rfid_uid=rfid_uid,
                    status=ItemStatus.NOT_PAID.value,
                    expiration_date=(datetime.now() + timedelta(days=days_to_expire)).date()
                )
                session.add(item)
                logger.info(f"Добавлен тестовый товар: {name} ({rfid_uid})")
        except Exception as e:
            logger.error(f"Ошибка добавления тестового товара: {e}")

    def check_expiring_soon(self) -> List[Dict[str, Any]]:
        """Проверить товары, у которых скоро истекает срок годности (до 3 дней)"""
        expiring_items = []
        try:
            with self.db.get_session() as session:
                soon_expiring = session.query(TaggedItem).filter(
                    TaggedItem.expiration_date != None,
                    TaggedItem.status == ItemStatus.NOT_PAID.value,
                    TaggedItem.expiration_date <= date.today() + timedelta(days=3),
                    TaggedItem.expiration_date > date.today()
                ).all()

                for item in soon_expiring:
                    days_left = (item.expiration_date - date.today()).days
                    expiring_items.append({
                        'name': item.product.name,
                        'rfid_uid': item.rfid_uid,
                        'expiration_date': item.expiration_date,
                        'days_left': days_left
                    })

                # Отправляем уведомление, если есть товары
                if expiring_items:
                    message = "ТОВАРЫ СКОРО ПРОСРОЧАТСЯ:\n\n"
                    for item in expiring_items[:5]:  # Показываем первые 5
                        message += f"• {item['name']}: {item['days_left']} дней\n"

                    if len(expiring_items) > 5:
                        message += f"\n...и еще {len(expiring_items) - 5} товаров"

                    self.send_telegram_notification(message, "expiration")

                return expiring_items
        except Exception as e:
            logger.error(f"Ошибка проверки скорого истечения срока: {e}")
            return []

    async def check_all_conditions(self):
        """Проверить все условия: остатки, сроки годности, просроченные товары"""
        try:
            # 1. Проверяем просроченные товары
            expired = self.check_expired_items()

            # 2. Проверяем товары, у которых скоро истекает срок
            expiring = self.check_expiring_soon()

            # 3. Проверяем остатки через inventory service
            alerts = inventory_service.check_all_products()
            if alerts:
                message = "ПРОВЕРКА ЗАПАСОВ:\n\n"
                for alert in alerts[:5]:  # Показываем первые 5
                    message += f"{alert.message}\n\n"

                if len(alerts) > 5:
                    message += f"...и еще {len(alerts) - 5} предупреждений"

                await self.send_telegram_notification(message, "low_stock")

            # 4. Сводное уведомление
            total_issues = len(expired) + len(expiring) + len(alerts)
            if total_issues > 0:
                summary = f"СВОДКА ПРОВЕРКИ:\n"
                summary += f"• Просрочено: {len(expired)} товаров\n"
                summary += f"• Скоро просрочится: {len(expiring)} товаров\n"
                summary += f"• Проблемы с запасами: {len(alerts)} товаров\n"
                await self.send_telegram_notification(summary, "info")

        except Exception as e:
            logger.error(f"Ошибка проверки всех условий: {e}")

