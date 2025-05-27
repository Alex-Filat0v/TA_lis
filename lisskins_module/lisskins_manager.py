import aiohttp
from typing import Dict, Any, Optional, List


class LisskinsAPIModule:
    """
    Класс для работы с сайтом lis-skins через его API.

    Магические методы __aenter__ и __aexit__ помогают реализовать асинхронное использование объекта класса внутри
    контекстного менеджера async with.

    P.S. Подробнее про API можно прочитать тут: https://lis-skins-ru.stoplight.io/docs/lis-skins-ru-public-user-api/
    """
    def __init__(self, api_token: str):
        """
        Магический метод инициализации экземпляра класса, принимает API ключ.

        P.S. API ключ получить можно на сайте: https://lis-skins.com/ru/profile/api/

        Стандартные значения:

        JSON_URL - url на парсинг всех скинов в json формате с сайта.

        BUY_URL - url API для покупки скина.

        :param api_token: Ключ доступа к API сайта lis-skins.
        """
        if not api_token:
            raise ValueError("API ключ не задан")

        self.JSON_URL = "https://lis-skins.com/market_export_json/csgo.json"
        self.BUY_URL = "https://api.lis-skins.com/v1/market/buy"

        self.api_token = api_token #!
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self.api_token}"}
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    @staticmethod
    async def _collect_data(all_items: Optional[dict]) -> dict:
        """
        Метод для структурирования и сбора всей информации о скинах с парсинга сайта.

        :param all_items: Все предметы, которые спарсили с сайта лисскинс.
        :return: Преобразованный словарь с парсинга в словарь вида {"name": "...", "price": "..."}.
        """
        lis_items = {}
        for item in all_items:
            name = item.get("name", "")
            price = item.get("price", 0.0)

            if name not in lis_items:
                lis_items[name] = {
                    "min_price": price,
                }
            else:
                if price < lis_items[name]["min_price"]:
                    lis_items[name]["min_price"] = price
        return lis_items

    async def parse_with_json_request(self) -> dict:
        """
        Метод для парсинга всех скинов с сайта лисскинс через json запрос по API.

        :return: Спаршенные и преобразованные для дальнейшего использования данные с сайта.
        """
        # Ассинхронно делаем GET запрос через нашу сессию по url для парсинга всех скинов в json формате
        async with self.session.get(url=self.JSON_URL) as response:
            try:
                response.raise_for_status()
                resp = await response.json()
                data = await self._collect_data(resp)
                return data

            except Exception as e:
                print(f"Ошибка при попытке спарсить сайт лисскинс через json запрос: {e}")
                raise

    async def buy_skins(self, skin_ids: List[int], partner: str, token: str,
                        max_price: Optional[float] = None, skip_unavailable: bool = False) -> dict:
        """
        Метод для покупки указанных скинов для пользователя через API лисскинс.

        :param skin_ids: Список id скинов для покупки P.S. максимум 100 штук.
        :param partner: Значение 'partner' из Steam трейд ссылки пользователя.
        :param token: Значение 'token' из Steam трейд ссылки пользователя.
        :param max_price: Максимальная цена для покупки. По стандарту None.
        :param skip_unavailable: Игнорировать заблокированные скины при массовой покупке. По стандарту False.

        :return: Ответ от API c информацией о покупке.
        """
        # Проверяем чтобы в запросе на покупку было не больше 100 скинов, больше API не даст купить
        if len(skin_ids) > 100:
            raise ValueError("Максимальное количество скинов, доступное для покупки: 100")

        # Формируем тело запроса
        payload = {
            "ids": skin_ids,
            "partner": partner,
            "token": token,
            "skip_unavailable": skip_unavailable
        }

        # Если установленна максимальная цена - добавляем ее в тело запроса
        if max_price is not None:
            payload["max_price"] = max_price

        # Ассинхронно делаем POST запрос через нашу сессию по url для покупки, а в тело запроса вставляем сформированный
        # ранее список
        async with self.session.post(self.BUY_URL, json=payload) as response:
            response.raise_for_status()

            return await response.json()


async def buy(api):

    # Обязательно нужно заполнить эти данные для теста покупок
    skin_ids = []
    partner = ""
    token = ""

    # Не обязательные к заполнению данные для теста покупок
    max_price = None  # float | NONE
    skip_unavailable = False  # bool

    async with LisskinsAPIModule(api_token=api) as parser:
        resp = await parser.buy_skins(skin_ids, partner, token, max_price, skip_unavailable)

    print(resp)


async def main(api):
    start_time = datetime.now()

    async with LisskinsAPIModule(api_token=api) as parser:
        resp = await parser.parse_with_json_request()

    end_time = datetime.now()

    print(resp)
    print(f"Парсинг завершился за: {end_time - start_time}")
    print(f"Спарсил скинов: {len(resp)}")


if __name__ == "__main__":
    import asyncio
    from datetime import datetime

    API_TOKEN = ""
    asyncio.run(main(API_TOKEN))

    #asyncio.run(buy(API_TOKEN))
