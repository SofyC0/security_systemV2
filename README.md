Security System v2 — RFID-инвентарная система для магазина



RFID-система управления запасами товаров в магазине
С анти-выносом (защита от краж), учётом просроченных товаров, динамическими порогами остатков и уведомлениями в Telegram.

🚀 О проекте
Security System v2 — это современная RFID-инвентарная система, которая:

Отслеживает наличие товаров с помощью RFID-меток
Защищает от выноса неоплаченных товаров (тревога в Telegram)
Автоматически помечает товары как просроченные
Уведомляет о низких остатках и критических запасах
Отправляет ежедневные отчёты и алерты
Имеет Telegram-бот для быстрого мониторинга и управления

Проект построен на FastAPI + SQLAlchemy (асинхронно), с отдельным модулем для считывателя RFID (Arduino/ESP32) и интеграцией с Telegram.

🛠️ Основные возможности

Анти-вынос — неоплаченный товар при попытке выноса вызывает мгновенную тревогу
Авто-обновление статусов — просрочка, оплата, низкие остатки
Учёт остатков — динамические пороги (минимум, критический)
Telegram-бот — статус, история тревог, уведомления
Ежедневные проверки — проверка просрочки и алерты
Мок-ридер для тестов и разработки
Тесты (pytest + фабрики)


📦 Требования
Bashpython >= 3.12
uvicorn
fastapi
sqlalchemy[asyncio] + psycopg2-binary
pydantic
python-dotenv
telegram
pytest + pytest-asyncio
Установи зависимости:
Bashpip install -r requirements.txt

📁 Структура проекта
textsecurity_systemV2/
├── main.py                  # Точка входа (FastAPI)
├── arduino_reader.py        # Интерфейс к считывателю Arduino
├── scheduler.py             # Ежедневные задачи
├── config/
│   └── settings.py          # Переменные окружения
├── app/
│   ├── core/
│   │   ├── database.py      # Асинхронная БД
│   │   ├── models.py        # SQLAlchemy-модели (TaggedItem, CatalogProduct...)
│   │   ├── inventory_service.py
│   │   ├── services.py      # Главный RFIDService + AlarmManager
│   │   ├── bot_integration.py
│   │   └── factories.py     # Фабрики для тестов и скриптов
│   ├── hardware/
│   │   ├── rfid_reader.py
│   │   └── mock_reader.py
│   └── telegram_bot/
│       └── bot.py           # Telegram-бот
├── migrations/
│   └── versions/            # Alembic-миграции
├── tests/
│   ├── test_models.py
│   ├── test_factories.py
│   ├── test_inventory_notifications.py
│   └── conftest.py
├── logs/                    # Автоматически создаётся
├── .env                     # Переменные окружения (НЕ коммить!)
├── .gitignore
└── requirements.txt


🔧 Как использовать
Основные модули

main.py — API + Telegram-бот
arduino_reader.py — считывает метки с Arduino
scheduler.py — ежедневная проверка просрочки и алерты
app/core/services.py — бизнес-логика (RFIDService, AlarmManager)

Telegram-бот
После запуска бота используй команды:

/start — приветствие + клавиатура
/status — общая статистика
/stock — запасы и просрочка
/alarms — история тревог
/check_stock — ручная проверка остатков


🧪 Тесты
Bashpytest
Тесты покрывают модели, фабрики и уведомления о запасах.

🔒 Безопасность

Пароли, токены и конфиги — только в .env
Логи в папке logs/
БД защищена (psycopg2 + pool)
Telegram-бот только для администраторов


📜 Лицензия
MIT License — свободно используй, форкай, улучшай!

Спасибо за внимание!
Проект в разработке. Если есть вопросы — пиши в Issues или Pull Requests.
