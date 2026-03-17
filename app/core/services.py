import logging
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from dataclasses import dataclass

from sqlalchemy import select, update, and_
from sqlalchemy.orm import selectinload

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
    """Менеджер тревог (полностью синхронный, не требует БД)"""

    def __init__(self):
        self.active_alarms: Dict[str, AlarmEvent] = {}
        self.alarm_history: List[AlarmEvent] = []

    def add_alarm(self, rfid_uid: str, item_name: str) -> AlarmEvent:
        alarm = AlarmEvent(
            rfid_uid=rfid_uid,
            item_name=item_name,
            timestamp=datetime.now()
        )
        if rfid_uid in self.active_alarms:
            self.active_alarms[rfid_uid].timestamp = datetime.now()
            return self.active_alarms[rfid_uid]

        self.active_alarms[rfid_uid] = alarm
        self.alarm_history.append(alarm)
        logger.warning(f"НОВАЯ ТРЕВОГА: {item_name} (RFID: {rfid_uid})")
        return alarm

    def resolve_alarm(self, rfid_uid: str, resolved_by: str) -> bool:
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
        return list(self.active_alarms.values())

    def get_alarm_history(self, limit: int = 10) -> List[AlarmEvent]:
        return sorted(self.alarm_history, key=lambda x: x.timestamp, reverse=True)[:limit]


class RFIDService:
    def __init__(self, db, alarm_manager=None, telegram_bot=None):
        self.db = db
        self.alarm_manager = alarm_manager or AlarmManager()
        self.telegram_bot = telegram_bot
        self.last_check_time = datetime.now()
        # inventory_service будет установлен позже, чтобы избежать циклических импортов
        self.inventory_service = None

    async def send_telegram_notification(self, message: str, notification_type: str = "info"):
        """Отправить уведомление в Telegram (асинхронно)"""
        if not self.telegram_bot:
            logger.warning("Telegram бот не передан")
            return False

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
        return True

    async def get_all_categories(self) -> List[str]:
        async with self.db.get_session() as session:
            result = await session.execute(select(CatalogProduct.category).distinct())
            return [row[0] for row in result if row[0]]

    async def get_items_by_category(self, category: str) -> List[Dict[str, Any]]:
        async with self.db.get_session() as session:
            stmt = select(TaggedItem).options(selectinload(TaggedItem.product)).join(CatalogProduct).where(
                CatalogProduct.category == category
            )
            items = (await session.execute(stmt)).scalars().all()
            return [{
                'name': item.product.name,
                'rfid_uid': item.rfid_uid,
                'status': item.status,
                'expiration_date': item.expiration_date.strftime('%d.%m.%Y') if item.expiration_date else None,
            } for item in items]

    async def get_expired_items_info(self) -> List[Dict[str, Any]]:
        async with self.db.get_session() as session:
            stmt = select(TaggedItem).options(selectinload(TaggedItem.product)).where(
                TaggedItem.expiration_date < date.today(),
                TaggedItem.status == ItemStatus.EXPIRED.value
            )
            items = (await session.execute(stmt)).scalars().all()
            return [{
                'name': item.product.name,
                'rfid_uid': item.rfid_uid,
                'expiration_date': item.expiration_date.strftime('%d.%m.%Y') if item.expiration_date else None,
            } for item in items]

    async def check_expired_items(self) -> List[str]:
        expired_tags = []
        async with self.db.get_session() as session:
            stmt = select(TaggedItem).options(selectinload(TaggedItem.product)).where(
                TaggedItem.expiration_date < date.today(),
                TaggedItem.status != ItemStatus.EXPIRED.value
            )
            expired_items = (await session.execute(stmt)).scalars().all()

            for item in expired_items:
                old_status = item.status
                item.status = ItemStatus.EXPIRED.value
                expired_tags.append(item.rfid_uid)
                await self._log_status_change(
                    session, item.rfid_uid, old_status, ItemStatus.EXPIRED.value, "expiry_check"
                )
                await self.send_telegram_notification(
                    f"ТОВАР ПРОСРОЧЕН!\n{item.product.name} (RFID: {item.rfid_uid})\nДата истечения: {item.expiration_date}",
                    "expiration"
                )

            if expired_items:
                logger.warning(f"Обновлено статусов просрочки: {len(expired_items)}")
                await self.send_telegram_notification(
                    f"ОБНАРУЖЕНО {len(expired_items)} ПРОСРОЧЕННЫХ ТОВАРОВ!", "expiration"
                )

        return expired_tags

    async def process_detected_tags(self, tag_ids: List[str]) -> bool:
        if not tag_ids:
            return False

        async with self.db.get_session() as session:
            stmt = select(TaggedItem).options(selectinload(TaggedItem.product)).where(
                TaggedItem.rfid_uid.in_(tag_ids)
            )
            items = (await session.execute(stmt)).scalars().all()

            if not items:
                return False

            unpaid_items = [item for item in items if item.status == ItemStatus.NOT_PAID.value]

            for item in items:
                if item.expiration_date:
                    days_left = (item.expiration_date - date.today()).days
                    if 0 < days_left <= 3:
                        await self.send_telegram_notification(
                            f"Товар '{item.product.name}' (RFID: {item.rfid_uid}) скоро просрочится!\nОсталось: {days_left} дней",
                            "expiration"
                        )

                # Проверка остатков через inventory_service
                if self.inventory_service:
                    qty = await self.inventory_service.get_current_quantity(item.product.product_id)
                    if qty <= getattr(item.product, 'critical_threshold', 5):
                        await self.send_telegram_notification(
                            f"КРИТИЧЕСКИ МАЛО ТОВАРА!\n{item.product.name}: осталось {qty} {item.product.unit}",
                            "critical_stock"
                        )
                    elif qty <= item.product.min_threshold:
                        await self.send_telegram_notification(
                            f"ЗАКАНЧИВАЕТСЯ ТОВАР!\n{item.product.name}: осталось {qty} {item.product.unit}",
                            "low_stock"
                        )

                await self._log_status_change(
                    session, item.rfid_uid, item.status, item.status, "antenna_scan"
                )

            if unpaid_items:
                for item in unpaid_items:
                    self.alarm_manager.add_alarm(item.rfid_uid, item.product.name)
                    await self.send_telegram_notification(
                        f"ТРЕВОГА! Обнаружен неоплаченный товар:\n{item.product.name}\nRFID: {item.rfid_uid}",
                        "alarm"
                    )
                logger.warning(f"ТРЕВОГА! Обнаружено {len(unpaid_items)} неоплаченных товаров")
                return True
            else:
                logger.info("Все товары оплачены или просрочены")
                return False

    async def _log_status_change(self, session, rfid_uid: str, old_status: str, new_status: str, change_source: str):
        history = ItemHistory(
            rfid_uid=rfid_uid,
            old_status=old_status,
            new_status=new_status,
            change_source=change_source
        )
        session.add(history)

    async def mark_as_paid(self, tag_ids: List[str], cashier: str = "system") -> None:
        if not tag_ids:
            return

        async with self.db.get_session() as session:
            stmt = select(TaggedItem).options(selectinload(TaggedItem.product)).where(
                TaggedItem.rfid_uid.in_(tag_ids)
            )
            items = (await session.execute(stmt)).scalars().all()

            for item in items:
                old_status = item.status
                item.status = ItemStatus.PAID.value
                await self._log_status_change(
                    session, item.rfid_uid, old_status, ItemStatus.PAID.value, f"cashier_{cashier}"
                )

                if item.rfid_uid in self.alarm_manager.active_alarms:
                    self.alarm_manager.resolve_alarm(item.rfid_uid, cashier)

                # Уменьшаем остаток через inventory_service (если есть)
                if self.inventory_service:
                    qty = await self.inventory_service.get_current_quantity(item.product.product_id)
                    # Здесь можно добавить логику обновления, если нужно

            logger.info(f"Помечено как оплачено: {len(items)} товаров (кассир: {cashier})")

    async def get_system_stats(self) -> Dict[str, Any]:
        async with self.db.get_session() as session:
            total = await session.scalar(select(func.count(TaggedItem.item_id)))
            not_paid = await session.scalar(
                select(func.count(TaggedItem.item_id)).where(TaggedItem.status == ItemStatus.NOT_PAID.value)
            )
            paid = await session.scalar(
                select(func.count(TaggedItem.item_id)).where(TaggedItem.status == ItemStatus.PAID.value)
            )
            expired = await session.scalar(
                select(func.count(TaggedItem.item_id)).where(TaggedItem.status == ItemStatus.EXPIRED.value)
            )

            recent = (await session.execute(
                select(ItemHistory).order_by(ItemHistory.change_time.desc()).limit(5)
            )).scalars().all()

            events_list = [{
                'rfid_uid': e.rfid_uid,
                'event': f"{e.old_status or '?'} → {e.new_status}",
                'time': e.change_time.isoformat()
            } for e in recent]

            return {
                'total_items': total or 0,
                'not_paid_items': not_paid or 0,
                'paid_items': paid or 0,
                'expired_items': expired or 0,
                'recent_events': events_list
            }

    async def search_item(self, rfid_uid: str) -> Optional[Dict[str, Any]]:
        async with self.db.get_session() as session:
            stmt = select(TaggedItem).options(selectinload(TaggedItem.product)).where(TaggedItem.rfid_uid == rfid_uid)
            item = (await session.execute(stmt)).scalar_one_or_none()
            if not item:
                return None

            history_stmt = select(ItemHistory).where(ItemHistory.rfid_uid == rfid_uid).order_by(ItemHistory.change_time.desc())
            history_rows = (await session.execute(history_stmt)).scalars().all()
            history_list = [{
                'time': h.change_time.isoformat(),
                'old_status': h.old_status,
                'new_status': h.new_status,
                'source': h.change_source
            } for h in history_rows]

            return {
                'name': item.product.name,
                'rfid_uid': item.rfid_uid,
                'status': item.status,
                'expiration_date': item.expiration_date.isoformat() if item.expiration_date else None,
                'last_seen': item.last_seen.isoformat() if item.last_seen else None,
                'history': history_list
            }

    def resolve_alarm(self, rfid_uid: str, resolved_by: str) -> bool:
        return self.alarm_manager.resolve_alarm(rfid_uid, resolved_by)

    async def add_test_item(self, name: str, rfid_uid: str, days_to_expire: int = 30):
        async with self.db.get_session() as session:
            # Предположим, что продукт уже есть с таким именем или создадим заглушку
            prod_stmt = select(CatalogProduct).where(CatalogProduct.name == name)
            product = (await session.execute(prod_stmt)).scalar_one_or_none()
            if not product:
                product = CatalogProduct(sku=f"TEST_{rfid_uid}", name=name)
                session.add(product)
                await session.flush()

            item = TaggedItem(
                product_id=product.product_id,
                rfid_uid=rfid_uid,
                status=ItemStatus.NOT_PAID.value,
                expiration_date=(datetime.now() + timedelta(days=days_to_expire)).date()
            )
            session.add(item)
            logger.info(f"Добавлен тестовый товар: {name} ({rfid_uid})")

    async def check_expiring_soon(self) -> List[Dict[str, Any]]:
        expiring_items = []
        async with self.db.get_session() as session:
            soon_expiring = (await session.execute(
                select(TaggedItem).options(selectinload(TaggedItem.product)).where(
                    TaggedItem.expiration_date != None,
                    TaggedItem.status == ItemStatus.NOT_PAID.value,
                    TaggedItem.expiration_date <= date.today() + timedelta(days=3),
                    TaggedItem.expiration_date > date.today()
                )
            )).scalars().all()

            for item in soon_expiring:
                days_left = (item.expiration_date - date.today()).days
                expiring_items.append({
                    'name': item.product.name,
                    'rfid_uid': item.rfid_uid,
                    'expiration_date': item.expiration_date,
                    'days_left': days_left
                })

            if expiring_items:
                message = "ТОВАРЫ СКОРО ПРОСРОЧАТСЯ:\n\n" + "\n".join(
                    f"• {item['name']}: {item['days_left']} дней" for item in expiring_items[:5]
                )
                if len(expiring_items) > 5:
                    message += f"\n\n...и еще {len(expiring_items) - 5} товаров"
                await self.send_telegram_notification(message, "expiration")

        return expiring_items

    async def check_all_conditions(self):
        """Проверить все условия: остатки, сроки годности, просроченные товары"""
        try:
            expired = await self.check_expired_items()
            expiring = await self.check_expiring_soon()

            alerts = []
            if self.inventory_service:
                alerts = await self.inventory_service.check_all_products()

            if alerts:
                message = "ПРОВЕРКА ЗАПАСОВ:\n\n" + "\n".join(a.message for a in alerts[:5])
                if len(alerts) > 5:
                    message += f"\n\n...и еще {len(alerts) - 5} предупреждений"
                await self.send_telegram_notification(message, "low_stock")

            total_issues = len(expired) + len(expiring) + len(alerts)
            if total_issues > 0:
                summary = (
                    f"СВОДКА ПРОВЕРКИ:\n"
                    f"• Просрочено: {len(expired)} товаров\n"
                    f"• Скоро просрочится: {len(expiring)} товаров\n"
                    f"• Проблемы с запасами: {len(alerts)} товаров\n"
                )
                await self.send_telegram_notification(summary, "info")
        except Exception as e:
            logger.error(f"Ошибка проверки всех условий: {e}")