import sys
from pathlib import Path

# Добавляем src/ в PYTHONPATH для тестов
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from parser import _make_id  # noqa: E402


def test_make_id_is_deterministic():
    rec = {
        "locality": "Гатчина",
        "address": "ул. Ленина, 15",
        "start": "15.03.2026 09:00",
        "end":   "15.03.2026 17:00",
    }
    assert _make_id(rec) == _make_id(rec)


def test_make_id_changes_on_different_data():
    a = {"locality": "Гатчина", "address": "A", "start": "1", "end": "2"}
    b = {"locality": "Гатчина", "address": "B", "start": "1", "end": "2"}
    assert _make_id(a) != _make_id(b)