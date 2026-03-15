# app/core/factories.py
"""
Фабрики сервисов — чтобы скрипты запускались самостоятельно без глобальных переменных
"""

from app.core.database import db

# Импортируем классы
from app.core.inventory_service import InventoryService
from app.core.services import RFIDService, AlarmManager


def get_inventory_service():
    """Создаёт свежий сервис запасов"""
    return InventoryService(db=db)


def get_rfid_service():
    """Создаёт свежий RFID-сервис"""
    return RFIDService(
        db=db,
        alarm_manager=AlarmManager(),
        telegram_bot=None   # бот не нужен в standalone-скриптах
    )