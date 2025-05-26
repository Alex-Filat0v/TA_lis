import re
import urllib.parse
import nest_asyncio
nest_asyncio.apply()
import asyncio
import requests
import urllib.parse
from datetime import datetime, timezone
from dateutil import parser as dateparser

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    JobQueue,
    Job,
)

########################################
# 1. НАСТРОЙКИ
########################################

TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID   = ""


API_URL = ""
API_PASSWORD = ""

LIS_URLS = {
    "cs2_unlocked": "https://lis-skins.com/market_export_json/api_csgo_unlocked.json",
    "rust_unlocked": "https://lis-skins.com/market_export_json/api_rust_unlocked.json",
    "dota2_unlocked": "https://lis-skins.com/market_export_json/api_dota2_unlocked.json",
}

STEAM_SALE_FACTOR = 0.87
USD_CONVERSION = 1
PROFIT_THRESHOLD_PERCENT = 17.5
JOB_INTERVAL_SECONDS = 400
TELEGRAM_DELAY = 10

########################################
# 2. API ДАННЫЕ
########################################

def get_api_data():
    headers = {"X-Password": API_PASSWORD}
    try:
        response = requests.get(API_URL, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        cs_list = []
        rust_list = []
        dota_list = []
        for item in data:
            if item.get("week_count", 0) > 100:
                mapped_item = {
                    "itemname": urllib.parse.unquote(item.get("item_name", "")),
                    "autobuy": float(item.get("sell_order", 0))
                }
                game_cat = item.get("game_cat", "").upper()
                if game_cat == "CS":
                    cs_list.append(mapped_item)
                elif game_cat == "RUST":
                    rust_list.append(mapped_item)
                elif game_cat == "DOTA":
                    dota_list.append(mapped_item)
        return {
            "aggregator_steam_cs2": cs_list,
            "aggregator_steam_rust": rust_list,
            "aggregator_steam_dota2": dota_list,
        }
    except Exception as e:
        print(f"[ERROR] Не удалось получить данные с API: {e}")
        return {}

########################################
# 3. LIS ДАННЫЕ
########################################

def calculate_days_left(unlock_at_str):
    if not unlock_at_str:
        return 0
    try:
        unlock_dt = dateparser.isoparse(unlock_at_str)
        if unlock_dt.tzinfo is None:  # <- добавляем защиту
            unlock_dt = unlock_dt.replace(tzinfo=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        diff = unlock_dt - now_utc
        return max(diff.days, 0)
    except Exception as e:
        print(f"Ошибка вычисления days_left: {e}")
        return 0


def fetch_lis_items(url):
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "success":
            return []
        return data.get("items", [])
    except Exception as e:
        print(f"[ERROR] LIS API запрос не удался: {e}")
        return []

def fetch_lis_data():
    lis_data = {"cs2": {}, "rust": {}, "dota2": {}}

    # CS2
    all_cs2_items = fetch_lis_items(LIS_URLS["cs2_unlocked"])
    for item in all_cs2_items:
        name = item.get("name", "")
        price = float(item.get("price", 0))*82.4
        unlock_at = item.get("unlock_at")
        days_left = calculate_days_left(unlock_at)
        if name not in lis_data["cs2"] or price < lis_data["cs2"][name]["price"]:
            lis_data["cs2"][name] = {"price": price, "days_left": days_left}

    # Rust
    all_rust_items = fetch_lis_items(LIS_URLS["rust_unlocked"])
    for item in all_rust_items:
        name = item.get("name", "")
        price = float(item.get("price", 0))*82.4
        if name not in lis_data["rust"] or price < lis_data["rust"][name]["price"]:
            lis_data["rust"][name] = {"price": price, "days_left": 0}

    # Dota2
    all_dota_items = fetch_lis_items(LIS_URLS["dota2_unlocked"])
    for item in all_dota_items:
        name = item.get("name", "")
        price = float(item.get("price", 0))*82.4
        unlock_at = item.get("unlock_at")
        days_left = calculate_days_left(unlock_at)
        if name not in lis_data["dota2"] or price < lis_data["dota2"][name]["price"]:
            lis_data["dota2"][name] = {"price": price, "days_left": days_left}

    return lis_data

########################################
# 4. ПОДСЧЁТ ПРИБЫЛИ
########################################

def calc_profitable_items(steam_data: dict, market_data: dict):
    pairs = [
        ("aggregator_steam_cs2", "cs2"),
        ("aggregator_steam_rust", "rust"),
        ("aggregator_steam_dota2", "dota2"),
    ]
    found = []

    for steam_table, market_key in pairs:
        if steam_table not in steam_data:
            continue
        market_dict = market_data.get(market_key, {})

        for row in steam_data[steam_table]:
            item_name = row.get("itemname", "")
            autobuy = float(row.get("autobuy", 0.0))
            if not item_name or item_name not in market_dict:
                continue

            mp = float(market_dict[item_name]["price"])
            if mp > 0:
                pr = ((autobuy * STEAM_SALE_FACTOR) - mp) / mp * 100
            else:
                pr = -9999
            if int(autobuy) - int(mp) < 7:
                continue
            if int(mp) < 10:
                continue
            if pr >= PROFIT_THRESHOLD_PERCENT:
                found.append({
                    "steam_table": steam_table,
                    "market_key": market_key,
                    "itemname": item_name,
                    "autobuy": round(autobuy, 2),
                    "market_price": round(mp, 2),
                    "profit_ratio": round(pr, 2)
                })
    return found

########################################
# 5. TELEGRAM СООБЩЕНИЯ
########################################

def CreateSteamMarketLink(item_name: str, steam_table: str) -> str:
    if steam_table == "aggregator_steam_cs2":
        base_url = "https://steamcommunity.com/market/listings/730/"
    elif steam_table == "aggregator_steam_rust":
        base_url = "https://steamcommunity.com/market/listings/252490/"
    elif steam_table == "aggregator_steam_dota2":
        base_url = "https://steamcommunity.com/market/listings/570/"
    else:
        base_url = "https://steamcommunity.com/market/listings/570/"
    encoded_item_name = urllib.parse.quote(item_name)
    return base_url + encoded_item_name

def CreateLisMarketLink(item_name: str, steam_table: str) -> str:
    formatted_name = item_name.lower()

    # Удаляем нежелательные символы, кроме точки
    formatted_name = re.sub(r"[|():]", "", formatted_name)

    # Пробелы → дефисы
    formatted_name = re.sub(r"\s+", "-", formatted_name)

    # Удаляем только символы, кроме букв/цифр/дефисов/подчёркиваний/точек (и сохраняем Unicode)
    formatted_name = re.sub(r"[^\w\-.]", "", formatted_name, flags=re.UNICODE)

    # Удаляем повторяющиеся дефисы
    formatted_name = re.sub(r"-{2,}", "-", formatted_name).strip("-")

    # Кодируем, оставляя дефисы и точки
    formatted_name = urllib.parse.quote(formatted_name, safe="-.")

    if steam_table == "aggregator_steam_cs2":
        return f"https://lis-skins.com/ru/market/csgo/{formatted_name}/"
    elif steam_table == "aggregator_steam_dota2":
        return f"https://lis-skins.com/ru/market/dota2/{formatted_name}/"
    elif steam_table == "aggregator_steam_rust":
        return f"https://lis-skins.com/ru/market/rust/{formatted_name}/"

    return "https://lis-skins.com"



async def send_item_as_message(context: ContextTypes.DEFAULT_TYPE, item: dict):
    steam_link = CreateSteamMarketLink(item["itemname"], item["steam_table"])
    lis_link = CreateLisMarketLink(item["itemname"], item["steam_table"])

    sale_price_usd = item["autobuy"] / USD_CONVERSION
    purchase_price_usd = item["market_price"] / USD_CONVERSION
    steam_sale_price_usd = (item["autobuy"] * STEAM_SALE_FACTOR) / USD_CONVERSION
    profit_usd = steam_sale_price_usd - purchase_price_usd

    profit_symbol = "🟩" if item["profit_ratio"] >= 15 else "🟨"
    game_tag = "#CS2" if item["steam_table"] == "aggregator_steam_cs2" else ("#Rust" if item["steam_table"] == "aggregator_steam_rust" else "#Dota2")

    text = (
        f"{profit_symbol} <b><a href='{lis_link}'>{item['itemname']}</a></b>\n"
        f"{profit_usd:.2f} RUB (+{item['profit_ratio']:.2f}% от цены покупки) - возможная чистая прибыль.\n"
        f"Ссылки на предмет: <a href='{lis_link}'>LIS</a>, <a href='{steam_link}'>Steam</a>\n"
        f"\nЦена покупки на LIS: {purchase_price_usd:.2f} RUB\n"
        f"Цена продажи Steam: {sale_price_usd:.2f} RUB\n"
        f"Цена продажи Steam с вычетом -13%: {steam_sale_price_usd:.2f} RUB\n"
        f"\nИгра: {game_tag}\n\n"
        "🟢 Бесплатный режим работы. Нет задержки вывода.\n"
        "❗️ Для показа скина нажмите на его название."
    )

    await context.bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

########################################
# 6. ФОНОВОЕ ЗАДАНИЕ
########################################

async def background_task_job(context: ContextTypes.DEFAULT_TYPE):
    print("[INFO] background_task_job: начинаем сбор и расчёт...")
    loop = asyncio.get_running_loop()
    steam_data = await loop.run_in_executor(None, get_api_data)
    market_data = await loop.run_in_executor(None, fetch_lis_data)

    if not steam_data:
        print("[INFO] steam_data пусто, завершаем.")
        return

    found_items = calc_profitable_items(steam_data, market_data)
    if found_items:
        await asyncio.sleep(10)
        for itm in found_items:
            await send_item_as_message(context, itm)
            await asyncio.sleep(TELEGRAM_DELAY)
    else:
        print("[INFO] Ничего выгодного не нашлось.")

    print("[INFO] background_task_job: закончено.")

########################################
# 7. ЗАПУСК
########################################

async def main():
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    job_queue = application.job_queue
    job_queue.run_repeating(
        background_task_job,
        interval=JOB_INTERVAL_SECONDS,
        first=5
    )

    print("[INFO] Запускаем бота (idle) ...")
    await application.run_polling()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
