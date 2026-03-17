import logging
import logging.handlers
import os
from pathlib import Path
from config.settings import settings

def setup_logging(name: str = "rfid_system") -> logging.Logger:
    """Настройка логирования с ротацией файлов и выводом в консоль"""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    log_dir = Path(settings.LOGS_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "system.log"

    # Формат логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Обработчик для файла с ротацией (10 файлов по 5 МБ)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5*1024*1024, backupCount=10, encoding='utf-8'
    )
    file_handler.setFormatter(formatter)

    # Обработчик для консоли
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Отдельный логгер для приложения
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    return logger