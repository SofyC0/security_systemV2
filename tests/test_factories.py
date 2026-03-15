from app.core.factories import get_inventory_service, get_rfid_service


def test_get_inventory_service():
    service = get_inventory_service()
    assert service is not None
    assert hasattr(service, "get_current_quantity")


def test_get_rfid_service():
    service = get_rfid_service()
    assert service is not None
    assert hasattr(service, "check_expired_items")  # или другие методы