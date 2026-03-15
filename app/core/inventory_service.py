import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

from app.core.database import db
from app.core.models import CatalogProduct, TaggedItem

logger = logging.getLogger(__name__)


@dataclass
class InventoryAlert:
    product_name: str
    current_quantity: int
    threshold: int
    alert_level: str  # "critical" или "warning"
    message: str


class InventoryService:
    def __init__(self, db):
        self.db = db
        self.sent_alerts = set()

    def update_quantity(self, sku: str, new_quantity: int) -> List[InventoryAlert]:
        """
        Этот метод больше не нужен в текущей модели.
        Количество считается динамически по tagged_items.
        Если нужно обновить количество конкретного экземпляра — используй другой метод.
        """
        logger.warning(f"update_quantity для sku={sku} вызван, но количество считается динамически")
        return []

    def get_current_quantity(self, product_id: int) -> int:
        """Подсчёт текущего количества по всем экземплярам"""
        with self.db.get_session() as session:
            return session.query(func.count(TaggedItem.item_id)).filter(
                TaggedItem.product_id == product_id,
                TaggedItem.status != ItemStatus.EXPIRED.value  # или твоя логика
            ).scalar() or 0

    def get_all_products(self) -> List[Dict[str, Any]]:
        """Возвращает список продуктов с динамическим количеством"""
        result = []
        try:
            with self.db.get_session() as session:
                products = session.query(CatalogProduct).all()

                for product in products:
                    current_qty = self.get_current_quantity(product.product_id)

                    result.append({
                        "sku": product.sku,
                        "name": product.name,
                        "current_quantity": current_qty,
                        "min_threshold": product.min_threshold,
                        "critical_threshold": product.critical_threshold,
                        "target_quantity": product.target_quantity,
                        "unit": product.unit,
                        "status": self._get_status(current_qty, product)
                    })
                return result
        except Exception as e:
            logger.error(f"Ошибка получения товаров: {e}")
            return []

    def _get_status(self, qty: int, product: CatalogProduct) -> str:
        if qty <= product.critical_threshold:
            return "critical"
        elif qty <= product.min_threshold:
            return "warning"
        elif qty <= product.target_quantity:
            return "normal"
        else:
            return "excess"

    def check_all_products(self) -> List[InventoryAlert]:
        alerts = []
        try:
            with self.db.get_session() as session:
                products = session.query(CatalogProduct).all()

                for product in products:
                    qty = self.get_current_quantity(product.product_id)
                    alerts.extend(self._check_thresholds(product, qty))
                return alerts
        except Exception as e:
            logger.error(f"Ошибка проверки товаров: {e}")
            return []

    def _check_thresholds(self, product: CatalogProduct, qty: int) -> List[InventoryAlert]:
        alerts = []
        if qty <= product.critical_threshold:
            alerts.append(InventoryAlert(
                product_name=product.name,
                current_quantity=qty,
                threshold=product.critical_threshold,
                alert_level="critical",
                message=f"🚨 КРИТИЧНО! {product.name}: {qty} {product.unit} (критично ≤ {product.critical_threshold})"
            ))
        elif qty <= product.min_threshold:
            alerts.append(InventoryAlert(
                product_name=product.name,
                current_quantity=qty,
                threshold=product.min_threshold,
                alert_level="warning",
                message=f"⚠️ Пора заказывать {product.name}: {qty} {product.unit} (≤ {product.min_threshold})"
            ))
        return alerts
