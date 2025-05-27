import aiomysql
from typing import Optional
import urllib.parse


class DatabaseModule:
    """
    Класс для работы с базой данных MySQL.
    """
    def __init__(self):
        """
        Магический метод инициализации экземпляра класса.
        """
        self.pool: Optional[aiomysql.Pool] = None

    @staticmethod
    async def _collect_rows(rows: dict) -> dict:
        """
        Метод для сбора из полученных данных - данных для отправки.
        :param rows: Строки из бд

        :return: Преобразованные строки из бд для дальнейшей работы
        """
        db_items = {}
        for row in rows:
            item_name_encoded = row["item_name"]
            corridor_avg = row["corridor_avg"]
            decoded_name = urllib.parse.unquote(item_name_encoded)
            db_items[decoded_name] = corridor_avg
        return db_items

    async def connect(self, host: str, port: int, user: str, password: str, db: str) -> None:
        """
        Метод для установки ассинхронного соединения с базой данных уже после создания экземпляра класса.

        :param host: IP хоста с базой данных, для локальной бд по стандарту: 127.0.0.1
        :param port: Порт хоста с базой данных, для локальной бд по стандарту: 3306
        :param user: Имя пользователя в базе данных, для локальной бд по стандарту: root
        :param password: Пароль для подключения к субд, задается пользователем при установке субд
        :param db: Имя базы данных
        """
        try:
            self.pool = await aiomysql.create_pool(
                host=host,
                port=port,
                user=user,
                password=password,
                db=db,
                autocommit=True,  # Ставим автокоммит для ускорения ответа и запросов
                echo=False,  # Отключаем логирование для ускорения
            )
            print("Подключение к MySQL произведено успешно")
        except Exception as e:
            print(f"При подключении к MySQL произошла ошибка: {e}")
            raise

    async def load_items(self, table_name: str = "cs2_sales_data_2025_02_03") -> dict:
        """
        Метод получения всех скинов из указанной таблицы по заданному запросу.
        :param table_name: Имя таблицы, откуда хотим получить данные, по стандарту стоит cs2_sales_data_2025_02_03, но надо бы исправить!!!
        :return: Полученные и преобразованные строки из базы
        """
        # Задаем запрос для поиска подходящих скинов, если нужно, то можно будет его потом отредактировать или
        # передавать в функцию как аргумент
        query = f"""
                SELECT item_name, corridor_avg
                FROM {table_name}
                WHERE passed_criteria = 1
                  AND corridor_avg > 0.1
            """

        # Ассинхронно из нашего подключения открываем коннектор и из него курсор и делаем запрос
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:

                try:
                    await cur.execute(query)
                    rows = await cur.fetchall()
                    db_items = await self._collect_rows(rows)

                    return db_items

                except Exception as e:
                    print(f"Ошибка при выполнении запроса к таблице из бд: {e}")
                    raise



async def main():
    db = DatabaseModule()

    await db.connect(
        host="127.0.0.1",
        port=3308,
        user="root",
        password="1234",
        db="ta"
    )
    table = "cs2_sales_data_2025_02_03"
    data = await db.load_items(table)
    print(data)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())


