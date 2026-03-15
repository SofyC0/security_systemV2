import serial
import serial.tools.list_ports
import time
import logging
logger = logging.getLogger(__name__)

class SerialRFIDReader:
    """Читает RFID-метки с Arduino через Serial порт"""

    def __init__(self, port=None, baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.connected = False

    def connect(self):
        """Подключается к Arduino. Если порт не указан, пытается найти Arduino автоматически."""
        if self.port is None:
            # Автоматический поиск Arduino по описанию или VID/PID
            ports = serial.tools.list_ports.comports()
            for p in ports:
                # Типичные строки для Arduino и CH340
                if any(key in p.description.lower() for key in ['arduino', 'ch340', 'usb serial', 'uart']):
                    self.port = p.device
                    logger.info(f"Найдено Arduino на порту: {self.port}")
                    break
            if self.port is None:
                logger.info("Не удалось найти Arduino автоматически. Укажите порт вручную.")
                return False

        try:
            logger.debug(f"Открываю порт {self.port}")
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(2)  # Ждём, пока Arduino перезагрузится после подключения
            self.connected = True
            logger.info(f"Подключено к {self.port}")
            return True
        except Exception as e:
            logger.info(f"Ошибка подключения: {e}")
            return False

    def read_tags(self):
        """Читает строки из Serial порта и возвращает список найденных UID."""
        if not self.connected or not self.ser:
            return []

        tags = []
        while self.ser.in_waiting > 0:
            try:
                line = self.ser.readline().decode('utf-8').strip()
                if line.startswith("UID:"):
                    uid = line.replace("UID:", "")
                    tags.append(uid)
                    logger.info(f"Считана метка: {uid}")
            except Exception as e:
                logger.error(f"Ошибка чтения: {e}")
        return tags

    def disconnect(self):
        if self.ser:
            self.ser.close()
            self.connected = False
            logger.info("Отключено от Arduino")