import asyncio
import sys

from aiogram.exceptions import TelegramConflictError

from app.main import main


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except TelegramConflictError:
        print("\n" + "=" * 50)
        print("❌ ОШИБКА: ОБНАРУЖЕН ВТОРОЙ ЭКЗЕМПЛЯР БОТА!")
        print("=" * 50 + "\n")
        sys.exit(1)
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")