import asyncio
import random
from typing import List, Dict


class SkinManager:
    """
    Класс для работы со скинами.
    """

    def __init__(self):
        """
        Магический метод инициализации экземпляра класса.
        """
        self.current_skins: List[Dict] = []
        self.lock = asyncio.Lock()

    async def update_skins(self, new_skins: List[Dict]) -> None:
        """
        Метод для обновления топ 500 самых выгодных скинов после парсинга.
        """
        async with self.lock:
            # Объединяем старые и новые скины
            combined_skins = self.current_skins + new_skins

            # Сортируем по убыванию прибыли и берем топ 500 самых выгодных
            combined_skins.sort(key=lambda x: x["profit_perc"], reverse=True)
            self.current_skins = combined_skins[:500]

            # Перемешиваем скины в случайном порядке
            random.shuffle(self.current_skins)

    async def get_skin_to_send(self) -> Dict | None:
        """
        Метод итерации по списку, возврата и удаление первого в списке скина из текущего списка.

        :return: Возвращает либо первый в списке скин и удаляет его из списка, либо None, если список пуст
        """
        async with self.lock:
            if not self.current_skins:
                return None
            return self.current_skins.pop(0)
