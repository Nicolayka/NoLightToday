import sys
from pathlib import Path

# Добавляем src/ в PYTHONPATH для тестов
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
import parser  # noqa: E402
from parser import FetchError, _make_id, _parse_table  # noqa: E402


NEW_TABLE = """
<table class="table--odd table--border table--top-center-bottom">
<thead><tr><th>Регион РФ / Район<br>или населенный пункт</th>
<th>Адрес</th><th>Дата и время отключения электроснабжения</th>
<th>Дата и время восстановления электроснабжения</th>
<th>Филиал</th><th>РЭС</th><th>Комментарий</th><th>ФИАС</th></tr></thead>
<tbody><tr id="bx_3218110189_218637">
<td><div class="column"><span>Ленинградская область</span>
<span>р-н Ломоносовский</span></div></td>
<td><div><span>д Петровское</span><span> тер. СНТ Фауна</span>
<span> ДНП Петровское поле</span></div></td>
<td><div><span>12-11-2026, 09:00</span></div></td>
<td><div><span>12-11-2026, 17:30</span></div></td>
<td>Пригородные ЭС</td><td>Ломоносовский РЭС</td>
<td>ВЛ-10кВ. Обрезка деревьев по трассе №62</td>
<td><span>04e60bd2-3f8b-4faf-9f76-0c0ea29aa92d</span><svg></svg></td>
</tr></tbody></table>
"""


def test_new_layout_preserves_fields_and_id():
    rec, = _parse_table(NEW_TABLE)
    assert rec["region"] == "Ленинградская область"
    assert rec["district"] == "р-н Ломоносовский"
    assert rec["address"] == "д Петровское тер. СНТ Фауна ДНП Петровское поле"
    assert rec["start"] == "12-11-2026 09:00"
    assert rec["end"] == "12-11-2026 17:30"
    assert rec["date_key"] == "12-11-2026"
    assert rec["branch"] == "Пригородные ЭС"
    assert rec["res"] == "Ломоносовский РЭС"
    assert rec["comment"] == "ВЛ-10кВ. Обрезка деревьев по трассе №62"
    assert rec["fias"] == "04e60bd2-3f8b-4faf-9f76-0c0ea29aa92d"
    legacy = '<table class="tableous_facts funds"><tbody><tr>' + ''.join(
        f'<td>{rec[key]}</td>' for key in (
            'region', 'district', 'address', 'start_date', 'start_time',
            'end_date', 'end_time', 'branch', 'res', 'comment', 'fias'
        )
    ) + '</tr></tbody></table>'
    assert _parse_table(legacy) == [rec]


def test_missing_table_is_error_but_empty_table_is_valid():
    with pytest.raises(FetchError):
        _parse_table('<html>Сервис временно недоступен</html>')
    assert _parse_table(NEW_TABLE[:NEW_TABLE.index('<tbody>')] +
                        '<tbody></tbody></table>') == []


def test_pagination_does_not_assume_fifty_rows_and_filters_archive(monkeypatch):
    from datetime import datetime

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 12, tzinfo=tz)

    monkeypatch.setattr(parser, 'datetime', FixedDatetime)
    monkeypatch.setattr(parser.time, 'sleep', lambda _: None)
    calls = []

    def fetch(street, page):
        calls.append((street, page))
        if page == 1:
            return NEW_TABLE.replace('12-11-2026', '11-11-2026')
        return NEW_TABLE

    monkeypatch.setattr(parser, '_fetch_page', fetch)
    records = parser.parse_outages(max_pages=5, street='СНТ Фауна')
    assert [r['start'] for r in records] == ['12-11-2026 09:00']
    assert calls == [('СНТ Фауна', 1), ('СНТ Фауна', 2), ('СНТ Фауна', 3)]


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
