import time
import random
from typing import List
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

class RFIDReader(ABC):
    """Абстрактный класс RFID-считывателя"""

    @abstractmethod
    def connect(self) -> bool:
        """Подключиться к считывателю"""
        pass

    @abstractmethod
    def read_tags(self) -> List[str]:
        """Прочитать метки в зоне действия"""
        pass


class MockRFIDReader(RFIDReader):
    """Заглушка RFID-считывателя для тестов"""

    def __init__(self, name: str = "Mock Reader"):
        self.name = name
        self.connected = False

        # Тестовые метки для симуляции
        self.mock_tags = [
            "RFID_7E3A5B1C",  # Молоко (не оплачено)
            "RFID_8F4B6C2D",  # Хлеб (не оплачено)
            "RFID_9A5C7D3E",  # Шоколад (не оплачено)
            "RFID_ABCD1234",  # Йогурт (оплачено)
            "RFID_EFGH5678",  # Чипсы (оплачено)
        ]

    def connect(self) -> bool:
        """Имитация подключения"""
        logger.info(f"Подключаюсь к {self.name}...")
        time.sleep(0.5)  # Имитация задержки
        self.connected = True
        logger.info("Подключение успешно")
        return True

    def read_tags(self) -> List[str]:
        """Имитация чтения меток"""
        if not self.connected:
            logger.warning("Считыватель не подключен!")
            return []

        # Случайное количество меток (1-3)
        num_tags = random.randint(1, 3)

        # Выбираем случайные метки
        detected = random.sample(self.mock_tags, num_tags)

        logger.info(f"Обнаружено меток: {num_tags}")
        logger.info(f"Метки: {detected}")

        return detected

    def simulate_shopping_scenario(self) -> List[str]:
        """Симуляция типичного сценария покупки"""
        scenarios = [
            ["RFID_7E3A5B1C"],  # Только молоко
            ["RFID_7E3A5B1C", "RFID_8F4B6C2D"],  # Молоко + хлеб
            ["RFID_ABCD1234"],  # Только оплаченный товар
            ["CC1A3A06", "E5873206"],  # Смесь оплаченных и неоплаченных
            [],  # Пустая корзина
        ]

        return random.choice(scenarios)