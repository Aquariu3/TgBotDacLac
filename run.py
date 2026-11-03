import asyncio
import sys

from aiogram.exceptions import TelegramConflictError

if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

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