import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL")
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    EXIT_ANTENNA_HOST = os.getenv("EXIT_ANTENNA_HOST", "localhost")
    EXIT_ANTENNA_PORT = int(os.getenv("EXIT_ANTENNA_PORT", "5060"))
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LOGS_DIR = os.path.join(BASE_DIR, "logs")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_CHAT_IDS = [int(x.strip()) for x in os.getenv("ADMIN_CHAT_IDS", "1352662222").split(",")]
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "system.log")

    def __init__(self):
        os.makedirs(self.LOGS_DIR, exist_ok=True)


settings = Settings()