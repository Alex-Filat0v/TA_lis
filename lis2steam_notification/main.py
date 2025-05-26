import sqlite3
import urllib.parse
import requests
import time
import json
import random
from dateutil import parser as dateparser
from datetime import datetime, timezone

########################################################################
# Константы
########################################################################
SALES_DB_FILE = "sales_data.db"   # <-- Ваша БД с тремя таблицами: 
                                  # cs2_sales_data_2025_01_11, rust_sales_data_2025_01_11, dota_sales_data_2025_01_11

# CS2
URL_CS2_UNLOCKED         = "https://lis-skins.com/market_export_json/api_csgo_unlocked.json"
URL_CS2_LOCKED_TEMPLATE  = "https://lis-skins.com/market_export_json/api_csgo_lock_{days}_days.json"

# Rust
URL_RUST_UNLOCKED        = "https://lis-skins.com/market_export_json/api_rust_unlocked.json"

# Dota2
URL_DOTA2_UNLOCKED       = "https://lis-skins.com/market_export_json/api_dota2_unlocked.json"
URL_DOTA2_LOCKED_TEMPLATE= "https://lis-skins.com/market_export_json/api_dota2_lock_{days}_days.json"

RESULT_JSON_FILE = "results.json"  # <-- Общий выходной JSON

# Телеграм
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID   = ""

########################################################################
# Словарь appid по game_id
########################################################################
APPID_MAP = {
    "cs2": "730",
    "rust": "252490",
    "dota2": "570",
}

########################################################################
# Функция повторной попытки GET-запроса
########################################################################
def fetch_url_with_retries(url, max_retries=5, timeout=20):
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp  # Успешно
        except requests.exceptions.RequestException as e:
            print(f"[Attempt {attempt}/{max_retries}] Ошибка при запросе {url}: {e}")
            if attempt == max_retries:
                return None
            time.sleep(1)  # небольшая задержка
    return None

########################################################################
# Функция получения items из JSON (универсальная)
########################################################################
def fetch_items(url) -> list:
    resp = fetch_url_with_retries(url)
    if resp is None:
        print(f"Не удалось получить ответ по URL: {url}")
        return []
    try:
        data = resp.json()
        if data.get("status") != "success":
            print(f"Статус не 'success' для URL={url}. Полный ответ: {data}")
            return []
        return data.get("items", [])
    except Exception as e:
        print(f"Ошибка парсинга JSON из {url}: {e}")
        return []

########################################################################
# Функция вычисления дней до разблокировки
########################################################################
def calculate_days_left(unlock_at_str) -> int:
    if not unlock_at_str:
        return 0
    try:
        unlock_dt = dateparser.isoparse(unlock_at_str)
        now_utc   = datetime.now(timezone.utc)
        diff = unlock_dt - now_utc
        days_left = diff.days
        return max(days_left, 0)
    except Exception as e:
        print(f"Ошибка вычисления days_left из строки '{unlock_at_str}': {e}")
        return 0

########################################################################
# Функция чтения предметов из БД
########################################################################
def load_items_from_db(table_name: str) -> dict:
    conn = sqlite3.connect(SALES_DB_FILE)
    cursor = conn.cursor()

    query = f"""
        SELECT item_name, corridor_avg
        FROM {table_name}
        WHERE passed_criteria = 1
          AND corridor_avg > 0.1
    """
    rows = cursor.execute(query).fetchall()
    conn.close()

    db_items = {}
    for row in rows:
        item_name_encoded = row[0]
        corridor_avg      = row[1]
        decoded_name      = urllib.parse.unquote(item_name_encoded)
        db_items[decoded_name] = corridor_avg

    return db_items

########################################################################
# Функция получения "минимальной цены" из LIS-skins для CS2
########################################################################
def get_cs2_lis_min_price() -> dict:
    items_unlocked = fetch_items(URL_CS2_UNLOCKED)
    items_locked   = []
    for i in range(1, 9):
        url = URL_CS2_LOCKED_TEMPLATE.format(days=i)
        locked_part = fetch_items(url)
        items_locked.extend(locked_part)

    all_items = items_unlocked + items_locked

    lis_items = {}
    for item in all_items:
        name       = item.get("name", "")
        price      = item.get("price", 0.0)
        unlock_at  = item.get("unlock_at")
        days_left  = calculate_days_left(unlock_at)

        if name not in lis_items:
            lis_items[name] = {
                "min_price": price,
                "days_left": days_left
            }
        else:
            if price < lis_items[name]["min_price"]:
                lis_items[name]["min_price"] = price
                lis_items[name]["days_left"] = days_left

    return lis_items

########################################################################
# Функция получения "минимальной цены" из LIS-skins для Rust
########################################################################
def get_rust_lis_min_price() -> dict:
    items_unlocked = fetch_items(URL_RUST_UNLOCKED)
    lis_items = {}
    for item in items_unlocked:
        name  = item.get("name", "")
        price = item.get("price", 0.0)
        if name not in lis_items:
            lis_items[name] = {
                "min_price": price,
                "days_left": 0
            }
        else:
            if price < lis_items[name]["min_price"]:
                lis_items[name]["min_price"] = price
    return lis_items

########################################################################
# Функция получения "минимальной цены" из LIS-skins для Dota2
########################################################################
def get_dota2_lis_min_price() -> dict:
    items_unlocked = fetch_items(URL_DOTA2_UNLOCKED)
    items_locked   = []
    for i in range(1, 8):
        url = URL_DOTA2_LOCKED_TEMPLATE.format(days=i)
        items_locked.extend(fetch_items(url))

    all_items = items_unlocked + items_locked
    lis_items = {}
    for item in all_items:
        name       = item.get("name", "")
        price      = item.get("price", 0.0)
        unlock_at  = item.get("unlock_at")
        days_left  = calculate_days_left(unlock_at)

        if name not in lis_items:
            lis_items[name] = {
                "min_price": price,
                "days_left": days_left
            }
        else:
            if price < lis_items[name]["min_price"]:
                lis_items[name]["min_price"] = price
                lis_items[name]["days_left"] = days_left

    return lis_items

########################################################################
# Функция отправки сообщения в Телеграм
########################################################################
def send_telegram_message(text: str, parse_mode: str = "Markdown"):
    """
    Отправляет сообщение в Телеграм-чат TELEGRAM_CHAT_ID, используя TELEGRAM_BOT_TOKEN.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Телеграм токен или чат-айди не заданы!")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Ошибка при отправке сообщения: {e}")

########################################################################
# Основная логика
########################################################################
def main():
    # 1. Загружаем предметы из БД (3 таблицы)
    cs2_db_items  = load_items_from_db("cs2_sales_data_2025_02_03")
    rust_db_items = load_items_from_db("rust_sales_data_2025_02_03")
    dota_db_items = load_items_from_db("dota_sales_data_2025_02_03")

    # 2. Получаем минимальные цены LIS-skins
    cs2_lis_items  = get_cs2_lis_min_price()
    rust_lis_items = get_rust_lis_min_price()
    dota_lis_items = get_dota2_lis_min_price()

    results = []

    # --- CS2 ---
    for item_name, corridor_avg in cs2_db_items.items():
        if item_name in cs2_lis_items:
            min_price = cs2_lis_items[item_name]["min_price"]
            days_left = cs2_lis_items[item_name]["days_left"]

            selling_after_fee = corridor_avg * 0.856
            ratio = selling_after_fee / min_price if min_price > 0 else 0

            if ratio >= 1.1:  # >= +10%
                profit_abs  = selling_after_fee - min_price
                profit_perc = (ratio - 1.0) * 100.0
                results.append({
                    "game_id": "cs2",
                    "item_name": item_name,
                    "days_left": days_left,
                    "corridor_avg": round(corridor_avg, 2),
                    "lis_min_price": round(min_price, 2),
                    "selling_after_fee": round(selling_after_fee, 2),
                    "profit_abs": round(profit_abs, 2),
                    "profit_perc": round(profit_perc, 2)
                })

    # --- Rust ---
    for item_name, corridor_avg in rust_db_items.items():
        if item_name in rust_lis_items:
            min_price = rust_lis_items[item_name]["min_price"]
            days_left = rust_lis_items[item_name]["days_left"]  # для Rust = 0

            selling_after_fee = corridor_avg * 0.856
            ratio = selling_after_fee / min_price if min_price > 0 else 0

            if ratio >= 1.1:
                profit_abs  = selling_after_fee - min_price
                profit_perc = (ratio - 1.0) * 100.0
                results.append({
                    "game_id": "rust",
                    "item_name": item_name,
                    "days_left": days_left,
                    "corridor_avg": round(corridor_avg, 2),
                    "lis_min_price": round(min_price, 2),
                    "selling_after_fee": round(selling_after_fee, 2),
                    "profit_abs": round(profit_abs, 2),
                    "profit_perc": round(profit_perc, 2)
                })

    # --- Dota2 ---
    for item_name, corridor_avg in dota_db_items.items():
        if item_name in dota_lis_items:
            min_price = dota_lis_items[item_name]["min_price"]
            days_left = dota_lis_items[item_name]["days_left"]

            selling_after_fee = corridor_avg * 0.856
            ratio = selling_after_fee / min_price if min_price > 0 else 0

            if ratio >= 1.1:
                profit_abs  = selling_after_fee - min_price
                profit_perc = (ratio - 1.0) * 100.0
                results.append({
                    "game_id": "dota2",
                    "item_name": item_name,
                    "days_left": days_left,
                    "corridor_avg": round(corridor_avg, 2),
                    "lis_min_price": round(min_price, 2),
                    "selling_after_fee": round(selling_after_fee, 2),
                    "profit_abs": round(profit_abs, 2),
                    "profit_perc": round(profit_perc, 2)
                })

    # 4. Сортируем results по проценту прибыли по убыванию
    results.sort(key=lambda x: x["profit_perc"], reverse=True)

    # 5. Сохраняем в JSON (можно не убирать, пусть остаётся для истории)
    with open(RESULT_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Итоговый файл {RESULT_JSON_FILE} сформирован, всего позиций: {len(results)}")

    # 6. Перемешаем результаты, чтобы отправлять вразнобой
    random.shuffle(results)

    # 7. Отправляем каждый предмет в Телеграм, с задержкой 2 секунды
    for r in results:
        game_id     = r["game_id"]
        item_name   = r["item_name"]
        days_left   = r["days_left"]
        corridor_avg= r["corridor_avg"]
        lis_min     = r["lis_min_price"]
        after_fee   = r["selling_after_fee"]
        profit_abs  = r["profit_abs"]
        profit_perc = r["profit_perc"]

        # Выберем нужный appid для ссылки
        appid = APPID_MAP.get(game_id, "730")  # пусть по умолчанию будет 730 (CS2), если нет в словаре

        # Название предмета для ссылки 
        # (В Markdown, если есть спецсимволы, желательно экранировать, но для простоты не делаем этого)
        # Ссылка будет: https://steamcommunity.com/market/listings/<appid>/<urlencoded_name>
        encoded_name = urllib.parse.quote(item_name)  # нужно именно url-encode для Steam Community
        steam_url    = f"https://steamcommunity.com/market/listings/{appid}/{encoded_name}"

        # Сформируем сообщение.
        # Пример оформления по вашему шаблону:
        # 
        # 🟩 🏅 [Neon Drop Box Storage](https://steamcommunity.com/market/listings/252490/Neon%20Drop%20Box%20Storage)
        # 👉🏻 Возможная цена продажи: 18.71$ (+10.21% от цены покупки)
        # Самый дешёвый лот: 16.97$
        # Продаётся за: 21.85$
        # 💰 Прибыль: 1.73$
        # Игровая категория: Rust
        # 🔒 Трейдлок: 3 д. (если days_left>0)
        #
        # ⚠️ Бесплатный режим работы...
        # 

        # Для наглядности показываем days_left только если >0, иначе скрываем
        trade_lock_str = ""
        if days_left > 0:
            trade_lock_str = f"🔒 Трейдлок: {days_left} д.\n"

        # Название игры для человека
        pretty_game_name = {
            "cs2":   "#CS2",
            "rust":  "#Rust",
            "dota2": "#Dota2"
        }.get(game_id, "CS2")

        # Собираем текст (Markdown)
        message_text = (
            f"🟩  [{item_name}]({steam_url})\n"
            f"🎮 Игра: {pretty_game_name}\n"
            f"👉🏻 Возможная цена продажи: {after_fee:.2f}$ (+{profit_perc:.2f}% от цены покупки)\n"
            f"Цена покупки: {lis_min:.2f}$\n"
            f"Цена продажи: {corridor_avg:.2f}$\n"
            f"💰 Прибыль: {profit_abs:.2f}$\n"
            f"{trade_lock_str}"
            "⚠️ Бесплатный режим работы. Задержка вывода 0 минут.\n"
            "❗️ Для показа скина нажмите на его название.\n"
            "✅ Для увеличения количества предметов, вывода без задержки, персональных настроек, автопокупки, "
            "сканирования нужных вам флоатов на предметах раз в несколько секунд — оформите подписку."
        )

        # Отправляем в Телеграм
        send_telegram_message(message_text, parse_mode="Markdown")

        # Задержка 2 секунды
        time.sleep(5.432)

if __name__ == "__main__":
    while True:
        main()
