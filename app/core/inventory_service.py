import logging
from typing import List, Dict, Any
from datetime import datetime
from dataclasses import dataclass

from sqlalchemy import select, func
from app.core.models import CatalogProduct, TaggedItem, ItemStatus

logger = logging.getLogger(__name__)


@dataclass
class InventoryAlert:
    product_name: str
    current_quantity: int
    threshold: int
    alert_level: str
    message: str


class InventoryService:
    def __init__(self, db):
        self.db = db
        self.sent_alerts = set()

    async def get_current_quantity(self, product_id: int) -> int:
        async with self.db.get_session() as session:
            stmt = select(func.count(TaggedItem.item_id)).where(
                TaggedItem.product_id == product_id,
                TaggedItem.status != ItemStatus.EXPIRED.value
            )
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def get_all_products(self) -> List[Dict[str, Any]]:
        result = []
        async with self.db.get_session() as session:
            stmt = select(CatalogProduct)
            products = (await session.execute(stmt)).scalars().all()

            for product in products:
                qty = await self.get_current_quantity(product.product_id)
                result.append({
                    "sku": product.sku,
                    "name": product.name,
                    "current_quantity": qty,
                    "min_threshold": product.min_threshold,
                    "critical_threshold": getattr(product, 'critical_threshold', 5),
                    "target_quantity": product.target_quantity,
                    "unit": product.unit,
                    "status": self._get_status(qty, product)
                })
        return result

    def _get_status(self, qty: int, product: CatalogProduct) -> str:
        if qty <= getattr(product, 'critical_threshold', 5):
            return "critical"
        elif qty <= product.min_threshold:
            return "warning"
        return "normal"

    async def check_all_products(self) -> List[InventoryAlert]:
        alerts = []
        async with self.db.get_session() as session:
            stmt = select(CatalogProduct)
            products = (await session.execute(stmt)).scalars().all()
            for product in products:
                qty = await self.get_current_quantity(product.product_id)
                if qty <= getattr(product, 'critical_threshold', 5):
                    alerts.append(InventoryAlert(
                        product_name=product.name,
                        current_quantity=qty,
                        threshold=getattr(product, 'critical_threshold', 5),
                        alert_level="critical",
                        message=f"🚨 КРИТИЧНО! {product.name}: {qty} {product.unit}"
                    ))
                elif qty <= product.min_threshold:
                    alerts.append(InventoryAlert(
                        product_name=product.name,
                        current_quantity=qty,
                        threshold=product.min_threshold,
                        alert_level="warning",
                        message=f"⚠️ Пора заказывать {product.name}: {qty} {product.unit}"
                    ))
        return alerts