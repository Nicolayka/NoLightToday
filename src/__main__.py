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


def _enable_system_certs_on_windows() -> None:
    """На Windows подменяет certifi на системное хранилище сертификатов.
    Решает ошибку SSLCertVerificationError / CERTIFICATE_VERIFY_FAILED.
    На Linux/macOS ничего не делает."""
    if sys.platform != "win32":
        return
    try:
        import pip_system_certs  # noqa: F401
    except ImportError:
        print(
            "[warn] pip-system-certs не установлен. "
            "Если ловите SSL-ошибки — выполните:\n"
            "       .venv\\Scripts\\python.exe -m pip install pip-system-certs"
        )


# Порядок важен: сначала SSL, потом UTF-8, потом импорт бота
_enable_system_certs_on_windows()
_force_utf8()

from bot import main  # noqa: E402


if __name__ == "__main__":
    asyncio.run(main())