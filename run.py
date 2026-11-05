import asyncio
import sys
import logging
import logging.handlers
import os

from aiogram.exceptions import TelegramConflictError

if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    # --- НАСТРОЙКА ЛОГИРОВАНИЯ (теперь до импорта app.main) ---
    log_file = os.path.join("data", "bot.log")
    os.makedirs("data", exist_ok=True)
    
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file, when="midnight", interval=1, backupCount=7, encoding="utf-8"
    )
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    
    logging.basicConfig(
        level=logging.INFO,
        handlers=[
            logging.StreamHandler(),
            file_handler
        ]
    )
    # -----------------------------------------------------------

    from app.main import main

    try:
        asyncio.run(main())
    except TelegramConflictError:
        print("\n" + "=" * 50)
        print("❌ ОШИБКА: ОБНАРУЖЕН ВТОРОЙ ЭКЗЕМПЛЯР БОТА!")
        print("=" * 50 + "\n")
        sys.exit(1)
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")