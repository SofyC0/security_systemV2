import time
import random
from typing import List
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

class RFIDReader(ABC):
    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def read_tags(self) -> List[str]:
        pass


class MockRFIDReader(RFIDReader):
    def __init__(self, name: str = "Mock Reader"):
        self.name = name
        self.connected = False
        self.mock_tags = [
            "RFID_7E3A5B1C",
            "RFID_8F4B6C2D",
            "RFID_9A5C7D3E",
            "RFID_ABCD1234",
            "RFID_EFGH5678",
        ]

    def connect(self) -> bool:
        logger.info(f"Подключаюсь к {self.name}...")
        time.sleep(0.5)
        self.connected = True
        logger.info("Подключение успешно")
        return True

    def read_tags(self) -> List[str]:
        if not self.connected:
            logger.warning("Считыватель не подключен!")
            return []
        num_tags = random.randint(1, 3)
        detected = random.sample(self.mock_tags, num_tags)
        logger.info(f"Обнаружено меток: {num_tags}")
        logger.info(f"Метки: {detected}")
        return detected

    def simulate_shopping_scenario(self) -> List[str]:
        scenarios = [
            ["RFID_7E3A5B1C"],
            ["RFID_7E3A5B1C", "RFID_8F4B6C2D"],
            ["RFID_ABCD1234"],
            ["CC1A3A06", "E5873206"],
            [],
        ]
        return random.choice(scenarios)