from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, Enum, ForeignKey, Text, CheckConstraint
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import enum

Base = declarative_base()


class ItemStatus(enum.Enum):
    NOT_PAID = "не_оплачен"
    PAID = "оплачен"
    EXPIRED = "просрочен"


class TaggedItem(Base):
    __tablename__ = 'tagged_items'

    item_id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('catalog_products.product_id'), nullable=False)
    rfid_uid = Column(String(100), unique=True, nullable=False)

    status = Column(String(20), nullable=False, default='не_оплачен')

    manufactured_date = Column(Date, nullable=True)
    expiration_date = Column(Date, nullable=True)
    last_seen = Column(DateTime, default=datetime.now)
    quantity = Column(Integer, default=1)

    created_at = Column(DateTime, default=datetime.now)

    product = relationship("CatalogProduct", back_populates="items")

    __table_args__ = (
        CheckConstraint(
            "status IN ('не_оплачен', 'оплачен', 'просрочен')",
            name='valid_status'
        ),
    )


class ItemHistory(Base):
    __tablename__ = 'item_history'

    history_id = Column(Integer, primary_key=True, autoincrement=True)
    rfid_uid = Column(String(100), nullable=False)
    old_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=False)
    change_time = Column(DateTime, default=datetime.now)
    change_source = Column(String(100), default="system")


class CatalogProduct(Base):
    __tablename__ = 'catalog_products'

    product_id = Column(Integer, primary_key=True)
    sku = Column(String(100), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    unit = Column(String(50), default="шт.")
    category = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)

    min_threshold = Column(Integer, default=10)
    target_quantity = Column(Integer, default=30)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    items = relationship("TaggedItem", back_populates="product", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CatalogProduct {self.sku}: {self.name}>"