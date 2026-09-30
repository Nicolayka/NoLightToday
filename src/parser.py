import hashlib
import time

import requests
from bs4 import BeautifulSoup

from config import BASE_URL, MAX_PAGES

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    )
}


def _make_id(rec: dict) -> str:
    raw = f"{rec['locality']}|{rec['address']}|{rec['start']}|{rec['end']}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def parse_outages(max_pages: int = MAX_PAGES) -> list[dict]:
    """Возвращает список отключений со всех страниц пагинации."""
    records: list[dict] = []
    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}?PAGEN_1={page}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[parser] страница {page}: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if not table:
            break

        rows = table.find_all("tr")[1:]
        if not rows:
            break

        for row in rows:
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) < 8:
                continue

            rec = {
                "region":   cols[0],
                "district": cols[1],
                "locality": cols[2],
                "address":  cols[3],
                "start":    f"{cols[4]} {cols[5]}",          # ДД.ММ.ГГГГ ЧЧ:ММ
                "end":      f"{cols[6]} {cols[7]}",
                "branch":   cols[8]  if len(cols) > 8  else "",
                "res":      cols[9]  if len(cols) > 9  else "",
                "comment":  cols[10] if len(cols) > 10 else "",
            }
            rec["id"] = _make_id(rec)
            rec["date_key"] = rec["start"].split()[0]
            records.append(rec)

        time.sleep(1)  # вежливая пауза между страницами

    return records