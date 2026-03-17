import serial
import serial.tools.list_ports
import time
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class SerialRFIDReader:
    def __init__(self, port: Optional[str] = None, baudrate: int = 9600, timeout: float = 1.0, reconnect_delay: float = 5.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.reconnect_delay = reconnect_delay
        self.ser: Optional[serial.Serial] = None
        self.connected: bool = False
        self._last_error_ts: float = 0.0

    def _auto_detect_port(self) -> bool:
        ports = serial.tools.list_ports.comports()
        candidates = []
        for p in ports:
            desc = p.description.lower()
            if any(keyword in desc for keyword in ['arduino', 'ch340', 'ch341', 'usb serial', 'uart', 'usb-serial']):
                candidates.append(p)
        if not candidates:
            logger.warning("Не удалось автоматически найти порт Arduino")
            return False
        self.port = candidates[0].device
        logger.info(f"Автоматически выбран порт: {self.port} ({candidates[0].description})")
        return True

    def connect(self) -> bool:
        if self.connected and self.ser and self.ser.is_open:
            return True
        if self.port is None:
            if not self._auto_detect_port():
                return False
        if not self.port:
            logger.error("Порт не указан и автоопределение не удалось")
            return False

        for attempt in range(1, 4):
            try:
                logger.info(f"Подключение к {self.port} (попытка {attempt}/3)")
                self.ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=self.timeout,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                )
                time.sleep(2.2)
                self.connected = True
                self._last_error_ts = 0.0
                logger.info(f"Успешно подключено к {self.port}")
                return True
            except Exception as e:
                logger.warning(f"Ошибка подключения: {e}")
                if attempt < 3:
                    time.sleep(2.0)
        logger.error(f"Не удалось подключиться к {self.port} после 3 попыток")
        self.connected = False
        return False

    def read_tags(self) -> List[str]:
        if not self.connected or not self.ser or not self.ser.is_open:
            if time.time() - self._last_error_ts > 30:
                logger.warning("Попытка чтения без активного соединения")
                self._last_error_ts = time.time()
            return []

        tags = []
        try:
            while self.ser.in_waiting > 0:
                line_bytes = self.ser.readline()
                try:
                    line = line_bytes.decode('utf-8', errors='replace').strip()
                except Exception:
                    continue
                if line.startswith("UID:"):
                    uid = line[4:].strip()
                    if uid:
                        tags.append(uid)
                        logger.info(f"Считана метка: {uid}")
            time.sleep(0.1)
        except Exception as e:
            logger.error(f"Ошибка чтения порта {self.port}: {e}")
            self.connected = False
        return tags

    def is_connected(self) -> bool:
        if self.ser and self.ser.is_open:
            self.connected = True
            return True
        self.connected = False
        return False

    def disconnect(self) -> None:
        if self.ser:
            try:
                self.ser.close()
                logger.info(f"Порт {self.port} закрыт")
            except Exception as e:
                logger.warning(f"Ошибка при закрытии порта {self.port}: {e}")
            finally:
                self.ser = None
                self.connected = False