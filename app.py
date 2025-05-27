import asyncio
import os
import urllib.parse
from dotenv import load_dotenv
from typing import List, Dict

from database_module.database_manager import DatabaseModule
from lisskins_module.lisskins_manager import LisskinsAPIModule
from telegram_module.telegram_manager import TelegramBot
from skin_module.skin_manager import SkinManager

load_dotenv()


async def parse_skins(db: DatabaseModule, lisskins_api_token: str) -> List[Dict]:
    """
    Функция парсинга скинов с лисскинса и получения толко выгодных скинов.

    :param db: Экземпляр класса DatabaseModule для обращения и работы с базой данных.
    :param lisskins_api_token: API ключ с сайта лисскинс.

    :return: Возвращает список со словарями, содержащими данные по выгодным скинам с лисскинс.
    """
    results = []

    # Собираем подходящие скины из базы данных
    cs2_db_items = await db.load_items("cs2_sales_data_2025_02_03")

    # Парсим данные по всем текущим предметам с сайта лисскинс
    async with LisskinsAPIModule(api_token=lisskins_api_token) as parser:
        cs2_lis_items = await parser.parse_with_json_request()

    # Собираем массив из всех скинов из базы данных
    for item_name, corridor_avg in cs2_db_items.items():

        # Проверяем есть ли этот предмет в списке скинов с лисскинса
        if item_name in cs2_lis_items:

            # Считаем прибыльность скина при покупке на сайте
            min_price = cs2_lis_items[item_name]["min_price"]
            selling_after_fee = corridor_avg * 0.856
            ratio = selling_after_fee / min_price if min_price > 0 else 0

            # Проверяем, если выгода больше 10% - добавляем скин в массив, который потом будем отправлять пользователям
            if 1.1 <= ratio <= 1.9:
                profit_abs = selling_after_fee - min_price
                profit_perc = (ratio - 1.0) * 100.0
                results.append({
                    "game_id": "cs2",
                    "item_name": item_name,
                    "corridor_avg": round(corridor_avg, 2),
                    "lis_min_price": round(min_price, 2),
                    "selling_after_fee": round(selling_after_fee, 2),
                    "profit_abs": round(profit_abs, 2),
                    "profit_perc": round(profit_perc, 2)
                })

    return results


def create_message(skin: Dict) -> str:
    """
    Функция для создания сообщения на отправку через бота в телеграм.

    :param skin: Словарь с информацией о скине.

    :return: Возвращает сообщение, которое будет отправлено в чат.
    """
    item_name = skin["item_name"]
    corridor_avg = skin["corridor_avg"]
    lis_min = skin["lis_min_price"]
    after_fee = skin["selling_after_fee"]
    profit_abs = skin["profit_abs"]
    profit_perc = skin["profit_perc"]

    encoded_name = urllib.parse.quote(item_name)
    steam_url = f"https://steamcommunity.com/market/listings/730/{encoded_name}"
    lisskins_url = f"https://lis-skins.com/ru/market/csgo/{item_name.lower().replace(' | ', '-').replace(' ', '-')
                                                                .replace('(', '').replace(')', '').replace('™', '')}"

    return (
        f"🟩 [{item_name}]({lisskins_url})\n"
        f"{profit_abs:.2f} USD (+{profit_perc:.2f}% от цены покупки) - возможная чистая прибыль.\n"
        f"Ссылки на предмет: [LIS]({lisskins_url}), [Steam]({steam_url})\n\n"
        f"Цена покупки на LIS: {lis_min:.2f} USD\n"
        f"Цена продажи Steam: {corridor_avg:.2f} USD\n"
        f"Цена продажи Steam с вычетом -13%: {after_fee} USD\n\n"
        f"Игра: #CS2\n\n"
        f"🟢 Бесплатный режим работы. Нет задержки вывода.\n"
        f"❗️ Для показа скина нажмите на его название."
    )


async def sending_loop(tg_bot: TelegramBot, skin_mgr: SkinManager) -> None:
    """
    Функция для бесконечной отправки выгодных скинов в чат с интервалом в 5 секунд.

    :param tg_bot: Экземпляр класса TelegramBot для отправки сообщения в чат.
    :param skin_mgr: Экземпляр класса SkinManager для получение скинов на отправку.
    """
    while True:
        skin = await skin_mgr.get_skin_to_send()
        if skin:
            message = create_message(skin)
            await tg_bot.send_message(message)
        await asyncio.sleep(5)


async def parsing_loop(db: DatabaseModule, skin_mgr: SkinManager, lisskins_api_token: str) -> None:
    """
    Функция для бесконечного парсинга скинов каждыйе 5 минут.

    :param db: Экземпляр класса DatabaseModule для работы с базой данных.
    :param skin_mgr: Экземпляр класса SkinManager для обновления топ 500 самых выгодных скинов.
    :param lisskins_api_token: API ключ с сайта лисскинс для обращения к нему при парсинге.
    """
    while True:
        new_skins = await parse_skins(db, lisskins_api_token)
        await skin_mgr.update_skins(new_skins)
        await asyncio.sleep(300)


async def main(db: DatabaseModule, tg_bot: TelegramBot, skin_mgr: SkinManager) -> None:
    """
    Основная функция, которая запускает процессы парсинга и отправки скинов.
    """
    # Загружаем API ключ лисскинса, а также данные для подключения к бд из переменных окружения.
    lisskins_api_token = os.getenv("LISSKINS_API_TOKEN")

    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME")

    # Подключаемся к базе данных
    await db.connect(
        host=db_host,
        port=int(db_port),
        user=db_user,
        password=db_password,
        db=db_name
    )

    # Параллельно запускаем задачу парсинга скинов и отправки этих скинов в чат
    await asyncio.gather(
        parsing_loop(db, skin_mgr, lisskins_api_token),
        sending_loop(tg_bot, skin_mgr)
    )


if __name__ == "__main__":
    try:
        # Загружаем токен бота и id чата из переменных окружения
        telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

        # Создаем экземпляры классов телеграм бота, коннектора базы данных и менеджера скинов
        telegram_bot = TelegramBot(telegram_bot_token, telegram_chat_id)
        database = DatabaseModule()
        skin_manager = SkinManager()

        # Запускаем основную функцию main
        asyncio.run(main(database, telegram_bot, skin_manager))

    except KeyboardInterrupt:
        pass
