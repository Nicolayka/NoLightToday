"""Диагностика: что видит Selenium на странице.

Использование:
    .venv\\Scripts\\python.exe scripts\\debug_html.py
    .venv\\Scripts\\python.exe scripts\\debug_html.py "СНТ Фауна"
"""
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

BASE_URL = "https://rosseti-lenenergo.ru/planned_work/"
OUT_DIR = Path(__file__).resolve().parent.parent / "debug"
OUT_DIR.mkdir(exist_ok=True)


def main():
    street = sys.argv[1] if len(sys.argv) > 1 else ""

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1600,2400")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts,
    )

    try:
        print(f"[debug] открываю {BASE_URL}")
        driver.get(BASE_URL)

        # Ждём хоть какой-то таблицы
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
            print("[debug] таблица обнаружена в DOM")
        except Exception:
            print("[debug] ⚠ таблица так и не появилась за 20 сек")

        time.sleep(3)   # даём JS дорисовать

        if street:
            print(f"[debug] ищу поле для ввода '{street}'...")
            candidates = driver.find_elements(
                By.CSS_SELECTOR, "input[type='text'], input:not([type])"
            )
            print(f"[debug] найдено input-полей: {len(candidates)}")
            for i, el in enumerate(candidates):
                name = el.get_attribute("name") or ""
                placeholder = el.get_attribute("placeholder") or ""
                print(f"  [{i}] name='{name}' placeholder='{placeholder}'")

            # Пытаемся найти поле с именем street или по плейсхолдеру
            field = None
            for el in candidates:
                name = (el.get_attribute("name") or "").lower()
                ph = (el.get_attribute("placeholder") or "").lower()
                if "street" in name or "населённый" in ph or "адрес" in ph:
                    field = el
                    break

            if field:
                print("[debug] ввожу значение в найденное поле")
                field.clear()
                field.send_keys(street)
                # Отправляем форму
                field.submit()
                time.sleep(5)
            else:
                print("[debug] ⚠ поле для ввода 'street' не найдено")

        # Сохраняем HTML и скриншот
        html_path = OUT_DIR / "page.html"
        png_path = OUT_DIR / "page.png"
        html_path.write_text(driver.page_source, encoding="utf-8")
        driver.save_screenshot(str(png_path))
        print(f"[debug] HTML сохранён: {html_path}")
        print(f"[debug] скриншот:    {png_path}")

        # Анализируем таблицы
        soup = BeautifulSoup(driver.page_source, "html.parser")
        tables = soup.find_all("table")
        print(f"\n[debug] всего <table> на странице: {len(tables)}")
        for i, t in enumerate(tables):
            rows = t.find_all("tr")
            print(f"\n=== Таблица #{i} ===")
            print(f"  строк: {len(rows)}")
            for j, row in enumerate(rows[:5]):
                cells = row.find_all(["td", "th"])
                texts = [c.get_text(strip=True)[:25] for c in cells]
                print(f"  [{j}] колонок: {len(cells)} | {texts}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()