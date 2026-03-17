import pytest
from datetime import datetime
from app.core.models import CatalogProduct, TaggedItem, ItemStatus


def test_create_catalog_product(db_session):
    product = CatalogProduct(
        sku="TEST-SKU-001",
        name="Тестовый товар",
        unit="шт.",
        min_threshold=5,
        target_quantity=20
    )
    db_session.add(product)
    db_session.commit()

    saved = db_session.query(CatalogProduct).filter_by(sku="TEST-SKU-001").first()
    assert saved is not None
    assert saved.name == "Тестовый товар"
    assert saved.min_threshold == 5


def test_create_tagged_item(db_session):
    product = CatalogProduct(sku="P001", name="Продукт")
    db_session.add(product)
    db_session.commit()

    item = TaggedItem(
        product_id=product.product_id,
        rfid_uid="ABC123DEF456",
        status=ItemStatus.NOT_PAID.value,
        manufactured_date=datetime.now()
    )
    db_session.add(item)
    db_session.commit()

    saved_item = db_session.query(TaggedItem).first()
    assert saved_item.rfid_uid == "ABC123DEF456"
    assert saved_item.status == "не_оплачен"