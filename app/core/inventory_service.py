import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

from app.core.database import db
from app.core.models import CatalogProduct

logger = logging.getLogger(__name__)


@dataclass
class InventoryAlert:
    """Оповещение о необходимости пополнения"""
    product_name: str
    current_quantity: int
    threshold: int
    alert_level: str  # "critical" или "warning"
    message: str


class InventoryService:
    """Упрощенный сервис для управления запасами (прототип)"""

    def __init__(self, db):
        self.db = db
        self.sent_alerts = set()  # Для предотвращения дублирования уведомлений

    def update_quantity(self, sku: str, new_quantity: int) -> List[InventoryAlert]:
        """
        Обновить количество товара и проверить пороги
        Возвращает список оповещений (если есть)
        """
        alerts = []

        try:
            with self.db.get_session() as session:

                product = session.query(CatalogProduct).filter_by(sku=sku).first()

                if not product:
                    logger.info(f"Товар с артикулом {sku} не найден")
                    return alerts

                old_quantity = product.current_quantity  # если поле осталось
                product.current_quantity = new_quantity
                product.updated_at = datetime.now()

                alerts = self._check_thresholds(product)
                logger.info(f"Обновлён товар {product.name}: {old_quantity} → {new_quantity}")
                return alerts
        except Exception as e:
            logger.error(f"Ошибка обновления количества: {e}")
            return []

    def _check_thresholds(self, product: CatalogProduct) -> List[InventoryAlert]:
        """Проверить, не пересек ли товар пороговые значения"""
        alerts = []
        alert_key = f"{product.sku}_{product.current_quantity}"

        # Если уведомление уже отправлялось для этого состояния - пропускаем
        if alert_key in self.sent_alerts:
            return alerts

        # Проверяем критические значения
        if product.current_quantity <= product.critical_threshold:
            alerts.append(InventoryAlert(
                product_name=product.name,
                current_quantity=product.current_quantity,
                threshold=product.critical_threshold,
                alert_level="critical",
                message=f"🚨 КРИТИЧЕСКИ МАЛО! {product.name}: осталось {product.current_quantity} {product.unit} (меньше {product.critical_threshold})"
            ))
            self.sent_alerts.add(alert_key)

        # Проверяем предупреждающие значения
        elif product.current_quantity <= product.min_threshold:
            alerts.append(InventoryAlert(
                product_name=product.name,
                current_quantity=product.current_quantity,
                threshold=product.min_threshold,
                alert_level="warning",
                message=f"⚠️ Пора заказывать! {product.name}: осталось {product.current_quantity} {product.unit} (меньше {product.min_threshold})"
            ))
            self.sent_alerts.add(alert_key)

        # Сбрасываем флаг отправки, если товар пополнили выше порога
        reset_keys = [k for k in self.sent_alerts if k.startswith(f"{product.sku}_")]
        for key in reset_keys:
            _, quantity = key.split("_")
            if int(quantity) < product.current_quantity:
                self.sent_alerts.remove(key)

        return alerts

    def add_product(self, sku: str, name: str,
                    rfid_uid: str = None,
                    current_quantity: int = 0,
                    min_threshold: int = 10,
                    critical_threshold: int = 5,
                    target_quantity: int = 30,
                    unit: str = "шт.") -> bool:
        """Добавить новый товар"""
        try:
            with self.db.get_session() as session:
                # Проверяем, не существует ли уже товар
                existing = session.query(CatalogProduct).filter_by(sku=sku).first()
                if existing:
                    logger.warning(f"Товар с артикулом {sku} уже существует")
                    return False

                product = CatalogProduct(
                    sku=sku,
                    name=name,
                    rfid_uid=rfid_uid,
                    current_quantity=current_quantity,
                    min_threshold=min_threshold,
                    critical_threshold=critical_threshold,
                    target_quantity=target_quantity,
                    unit=unit
                )

                session.add(product)
                logger.info(f"Добавлен товар: {name} ({sku})")
                return True

        except Exception as e:
            logger.error(f"Ошибка добавления товара: {e}")
            return False

    def get_all_products(self) -> List[Dict[str, Any]]:
        """Получить все товары"""
        try:
            with self.db.get_session() as session:
                products = session.query(CatalogProduct).order_by(CatalogProduct.name).all()

                result = []
                for product in products:
                    result.append({
                        "sku": product.sku,
                        "name": product.name,
                        "rfid_uid": product.rfid_uid,
                        "current_quantity": product.current_quantity,
                        "min_threshold": product.min_threshold,
                        "critical_threshold": product.critical_threshold,
                        "target_quantity": product.target_quantity,
                        "unit": product.unit,
                        "manufactured_date": product.manufactured_date,
                        "expiration_date": product.expiration_date,
                        "last_updated": product.updated_at,
                        "status": self._get_status(product)
                    })

                return result

        except Exception as e:
            logger.error(f"Ошибка получения товаров: {e}")
            return []

    def _get_status(self, product: CatalogProduct) -> str:
        """Определить статус товара"""
        if product.current_quantity <= product.critical_threshold:
            return "critical"
        elif product.current_quantity <= product.min_threshold:
            return "warning"
        elif product.current_quantity <= product.target_quantity:
            return "normal"
        else:
            return "excess"

    def check_all_products(self) -> List[InventoryAlert]:
        """Проверить все товары на пороги"""
        alerts = []

        try:
            with self.db.get_session() as session:
                products = session.query(CatalogProduct).all()

                for product in products:
                    product_alerts = self._check_thresholds(product)
                    alerts.extend(product_alerts)

                return alerts

        except Exception as e:
            logger.error(f"Ошибка проверки товаров: {e}")
            return []
