"""Точка входа: python -m src."""
import asyncio
import sys


def _force_utf8() -> None:
    """На Windows консоль по умолчанию cp1251 — эмодзи и русский текст падают.
    Переключаем stdout/stderr на UTF-8, если Python это поддерживает."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


_force_utf8()

from bot import main  # noqa: E402


if __name__ == "__main__":
    asyncio.run(main())