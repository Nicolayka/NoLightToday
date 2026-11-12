"""Парсер графика плановых работ Россети Ленэнерго.

Использует обычный GET к /clients/planned_work/ с параметрами формы.
Данные приходят в HTML-таблице: регион/район и дата/время объединены.
"""
import hashlib
import re
import time
from datetime import datetime, timedelta, timezone

import requests
import urllib3
from bs4 import BeautifulSoup

from config import BASE_URL, MAX_PAGES

MSK = timezone(timedelta(hours=3))

# Сайт Россети подписан сертификатом Минцифры, которого нет в certifi.
# Поэтому для запросов к нему проверка сертификата отключена,
# а предупреждение urllib3 об этом заглушено, чтобы не засорять логи.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
    """Ищет таблицу по заголовку либо по классам старой разметки."""
    for table in soup.find_all("table"):
        classes = table.get("class") or []
        if "tableous_facts" in classes or "funds" in classes:
            return table
        first_th = table.find("th")
        if first_th and "Регион РФ" in first_th.get_text(" ", strip=True):
            return table
    return None


def _parse_table(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = _find_data_table(soup)
    if not table:
        raise FetchError("таблица отключений не найдена — проверьте разметку сайта")

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
        cells = row.find_all("td")
        if len(cols) == 8:
            # Новая разметка: регион и район — отдельные span в одной ячейке.
            location = list(cells[0].stripped_strings)
            start = re.split(r",?\s+", cols[2], maxsplit=1)
            end = re.split(r",?\s+", cols[3], maxsplit=1)
            rec = {
                "region": location[0] if location else "",
                "district": " ".join(location[1:]),
                "address": cols[1],
                "start_date": start[0].rstrip(","),
                "start_time": start[1] if len(start) > 1 else "",
                "end_date": end[0].rstrip(","),
                "end_time": end[1] if len(end) > 1 else "",
                "branch": cols[4],
                "res": cols[5],
                "comment": cols[6],
                "fias": cols[7],
            }
        elif len(cols) >= 7:
            rec = {
                "region": cols[0], "district": cols[1], "address": cols[2],
                "start_date": cols[3], "start_time": cols[4],
                "end_date": cols[5], "end_time": cols[6],
                "branch": cols[7] if len(cols) > 7 else "",
                "res": cols[8] if len(cols) > 8 else "",
                "comment": cols[9] if len(cols) > 9 else "",
                "fias": cols[10] if len(cols) > 10 else "",
            }
        else:
            continue

        rec["start"]    = f"{rec['start_date']} {rec['start_time']}".strip()
        rec["end"]      = f"{rec['end_date']} {rec['end_time']}".strip()
        rec["locality"] = rec["district"]
        rec["date_key"] = rec["start_date"]
        rec["id"]       = _make_id(rec)
        records.append(rec)

    return records


def _fetch_page(street: str, page: int) -> str:
    """GET к /clients/planned_work/ с параметрами формы.

    Передаём сегодняшнюю дату по МСК. Новый сайт может игнорировать
    фильтр — архив дополнительно отсекается в parse_outages.
    """
    today = datetime.now(MSK).strftime("%d.%m.%Y")

    params = {
        "date_start":  today,
        "date_finish": "",
        "street":      street,
    }
    if page > 1:
        params["PAGEN_1"] = page

    try:
        r = requests.get(
            BASE_URL,
            headers=HEADERS,
            params=params,
            timeout=30,
            verify=False,  # сертификат Минцифры, см. комментарий выше
        )
        r.raise_for_status()
        return r.text
    except requests.RequestException as e:
        print(f"[parser] GET стр.{page}: {e}")
        return ""


class FetchError(Exception):
    """Не удалось загрузить страницу с сайта (сеть, SSL, HTTP-ошибка)."""


def parse_outages(max_pages: int = MAX_PAGES, street: str = "") -> list[dict]:
    """Возвращает список отключений.

    street=""      — все записи,
    street="СНТ X" — только те, где в поле «Адрес» есть «СНТ X».

    Если не загрузилась первая страница — бросает FetchError, чтобы
    вызывающий код отличал «отключений нет» от «сайт недоступен».
    Сбой на следующих страницах не фатален: вернётся то, что успели собрать.
    """
    all_records: list[dict] = []
    seen_ids: set[str] = set()

    for page in range(1, max_pages + 1):
        html = _fetch_page(street, page)
        if not html:
            if page == 1:
                raise FetchError(f"не удалось загрузить страницу для '{street}'")
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

        if page < max_pages:
            time.sleep(1)

    # Новый сайт может игнорировать date_start и возвращать архив.
    today = datetime.now(MSK).date()
    return [
        r for r in all_records
        if datetime.strptime(r["start_date"].replace(".", "-"), "%d-%m-%Y").date()
        >= today
    ]
