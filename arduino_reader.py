import serial
import serial.tools.list_ports
import time
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class SerialRFIDReader:
    """
    Класс для чтения RFID-меток с Arduino через Serial-порт.
    Содержит надёжную обработку ошибок, попытки переподключения и логирование.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 9600,
        timeout: float = 1.0,
        reconnect_delay: float = 5.0,
    ):
        self.port: Optional[str] = port
        self.baudrate: int = baudrate
        self.timeout: float = timeout
        self.reconnect_delay: float = reconnect_delay

        self.ser: Optional[serial.Serial] = None
        self.connected: bool = False
        self._last_error_ts: float = 0.0

    def _auto_detect_port(self) -> bool:
        """Пытается автоматически найти порт Arduino/CH340/CH341"""
        ports = serial.tools.list_ports.comports()
        candidates = []

        for p in ports:
            desc = p.description.lower()
            if any(keyword in desc for keyword in [
                'arduino', 'ch340', 'ch341', 'usb serial', 'uart', 'usb-serial'
            ]):
                candidates.append(p)

        if not candidates:
            logger.warning("Не удалось автоматически найти порт Arduino")
            return False

        # берём первый подходящий
        self.port = candidates[0].device
        logger.info(f"Автоматически выбран порт: {self.port} ({candidates[0].description})")
        return True

    def connect(self) -> bool:
        """
        Пытается открыть соединение с Arduino.
        Возвращает True при успехе, False при неудаче.
        """
        if self.connected and self.ser and self.ser.is_open:
            logger.debug("Соединение уже активно")
            return True

        # Если порт не задан — пытаемся найти автоматически
        if self.port is None:
            if not self._auto_detect_port():
                return False

        if not self.port:
            logger.error("Порт не указан и автоопределение не удалось")
            return False

        for attempt in range(1, 4):
            try:
                logger.info(f"Подключение к {self.port} (попытка {attempt}/{3})")
                self.ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=self.timeout,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                )

                # Важная пауза — Arduino часто перезагружается при открытии порта
                time.sleep(2.2)

                self.connected = True
                self._last_error_ts = 0.0
                logger.info(f"Успешно подключено к {self.port}")
                return True

            except serial.SerialException as e:
                logger.warning(f"SerialException при подключении: {e}")
            except PermissionError as e:
                logger.error(f"Нет прав доступа к порту {self.port}: {e}")
                return False  # дальше пытаться бессмысленно
            except Exception as e:
                logger.error(f"Неизвестная ошибка подключения: {type(e).__name__} → {e}")

            if attempt < 3:
                time.sleep(2.0)

        logger.error(f"Не удалось подключиться к {self.port} после 3 попыток")
        self.connected = False
        return False

    def read_tags(self) -> List[str]:
        """
        Читает все доступные строки из буфера порта и возвращает список UID-меток.
        Возвращает пустой список при ошибке или отсутствии данных.
        """
        if not self.connected or not self.ser or not self.ser.is_open:
            if time.time() - self._last_error_ts > 30:
                logger.warning("Попытка чтения без активного соединения")
                self._last_error_ts = time.time()
            return []

        tags: List[str] = []

        try:
            while self.ser.in_waiting > 0:
                line_bytes = self.ser.readline()
                try:
                    line = line_bytes.decode('utf-8', errors='replace').strip()
                except Exception as decode_err:
                    logger.warning(f"Ошибка декодирования строки: {decode_err}")
                    continue

                if line.startswith("UID:"):
                    uid = line[4:].strip()
                    if uid:
                        tags.append(uid)
                        logger.info(f"Считана метка: {uid}")
            time.sleep(0.1)

        except serial.SerialException as e:
            logger.error(f"Ошибка чтения порта {self.port}: {e}")
            self.connected = False
            # Можно здесь сразу запланировать переподключение, но лучше делать это снаружи

        except Exception as e:
            logger.exception(f"Неожиданная ошибка при чтении с {self.port}")
            self.connected = False

        return tags

    def is_connected(self) -> bool:
        """Проверяет, активно ли соединение в данный момент"""
        if self.ser and self.ser.is_open:
            self.connected = True
            return True

        self.connected = False
        return False

    def disconnect(self) -> None:
        """Безопасно закрывает порт, если он открыт"""
        if self.ser:
            try:
                self.ser.close()
                logger.info(f"Порт {self.port} закрыт")
            except Exception as e:
                logger.warning(f"Ошибка при закрытии порта {self.port}: {e}")
            finally:
                self.ser = None
                self.connected = False
