"""Парсер графика плановых работ Россети Ленэнерго.

Использует обычный GET к /planned_work/ с параметрами формы.
Данные приходят в HTML-таблице с классом 'tableous_facts funds'.
"""
import hashlib
import time

import requests
from bs4 import BeautifulSoup

from config import BASE_URL, MAX_PAGES

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Referer": BASE_URL,
}


def _make_id(rec: dict) -> str:
    raw = (
        f"{rec.get('district','')}|{rec.get('address','')}|"
        f"{rec.get('start','')}|{rec.get('end','')}"
    )
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _find_data_table(soup: BeautifulSoup):
    """Ищет таблицу с данными по классу или по заголовку 'Регион РФ'.

    Первая таблица на странице — форма фильтра, вторая — данные.
    Ориентируемся на класс 'tableous_facts' (или 'funds') либо на th с текстом.
    """
    for table in soup.find_all("table"):
        classes = table.get("class") or []
        if "tableous_facts" in classes or "funds" in classes:
            return table
        first_th = table.find("th")
        if first_th and "Регион РФ" in first_th.get_text():
            return table
    return None


def _parse_table(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = _find_data_table(soup)
    if not table:
        return []

    # Данные лежат в <tbody>, заголовки — в <thead>
    tbody = table.find("tbody")
    if not tbody:
        return []

    records: list[dict] = []

    for row in tbody.find_all("tr"):
        # separator=" " — чтобы «тер. СНТ Фауна» и «д Петровское» не склеивались
        cols = [
            td.get_text(separator=" ", strip=True)
            for td in row.find_all("td")
        ]
        if len(cols) < 7:
            continue

        rec = {
            "region":     cols[0],
            "district":   cols[1],
            "address":    cols[2],
            "start_date": cols[3],
            "start_time": cols[4],
            "end_date":   cols[5],
            "end_time":   cols[6],
            "branch":     cols[7]  if len(cols) > 7  else "",
            "res":        cols[8]  if len(cols) > 8  else "",
            "comment":    cols[9]  if len(cols) > 9  else "",
            "fias":       cols[10] if len(cols) > 10 else "",
        }

        rec["start"]    = f"{rec['start_date']} {rec['start_time']}".strip()
        rec["end"]      = f"{rec['end_date']} {rec['end_time']}".strip()
        rec["locality"] = rec["district"]
        rec["date_key"] = rec["start_date"]
        rec["id"]       = _make_id(rec)
        records.append(rec)

    return records


from datetime import date

def _fetch_page(street: str, page: int) -> str:
    """GET к /planned_work/ с параметрами формы.

    Без date_start сайт отдаёт только будущие отключения — добавляем
    сегодняшнюю дату, чтобы записи за сегодня тоже попадали в выдачу.
    """
    today = date.today().strftime("%d.%m.%Y")

    params = {
        "reg":         "",
        "city":        "",
        "date_start":  today,     # ← ключевое: включаем записи с сегодня
        "date_finish": "",
        "res":         "",
        "street":      street,
    }
    if page > 1:
        params["PAGEN_1"] = page

    try:
        r = requests.get(
            BASE_URL, headers=HEADERS, params=params, timeout=30
        )
        r.raise_for_status()
        return r.text
    except requests.RequestException as e:
        print(f"[parser] GET стр.{page}: {e}")
        return ""


def parse_outages(max_pages: int = MAX_PAGES, street: str = "") -> list[dict]:
    """Возвращает список отключений.

    street=""      — все записи,
    street="СНТ X" — только те, где в поле «Адрес» есть «СНТ X».
    """
    all_records: list[dict] = []
    seen_ids: set[str] = set()

    for page in range(1, max_pages + 1):
        html = _fetch_page(street, page)
        if not html:
            break

        page_records = _parse_table(html)
        print(
            f"[parser] street='{street or '(все)'}' стр.{page}: "
            f"{len(page_records)} записей"
        )

        if not page_records:
            break

        new_records = [r for r in page_records if r["id"] not in seen_ids]
        if not new_records:
            break

        for r in new_records:
            seen_ids.add(r["id"])
        all_records.extend(new_records)

        # Если на странице меньше 50 записей — следующей страницы нет
        if len(page_records) < 50:
            break

        time.sleep(1)

    return all_records