import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import db

async def main():
    if len(sys.argv) < 2:
        print("Использование: clear_chat.py <chat_id>")
        return
    await db.init_db()
    await db.clear_subscriptions(int(sys.argv[1]))
    print(f"[ok] подписки для chat_id={sys.argv[1]} удалены")

if __name__ == "__main__":
    asyncio.run(main())