import aiohttp


class TelegramBot:
    """
    Класс для работы с телеграм ботом, реализованный только на ассинхронных запросах.

    Метод send_message: отправляет сообщение в указанный при инициализации канал от лица бота
    """

    def __init__(self, bot_token, chat_id):
        """
        Магический метод инициализации экземпляра класса, принимает токен бота и id чата, в который нужно писать.

        :param bot_token: Токен бота в телеграм.
        :param chat_id: Id чата в телеграм.
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.session = None

    async def send_message(self, text: str) -> None:
        """
        Метод для отправки сообщения в канал от лица бота.
        :param text: Текст, который отправит бот в канал.
        """

        # Создаем ссылку и параметры для запроса
        url_for_request = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        parameters_for_request = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }

        # try - except для отлова непредвиденных ошибок
        try:
            # Открываем ассинхронную сессию для отправки сообщения
            self.session = aiohttp.ClientSession()
            response = await self.session.post(url_for_request, json=parameters_for_request)

            # Если сообщение не удалось отправить - выводим ошибку
            if response.status != 200:
                error = await response.text()
                print(f"Ошибка при отправке сообщения в телеграм: {error}")
        except Exception as e:
            print(f"Непредвиденная ошибка при отправке сообщения в телеграм: {e}")

        # После отправки сообщения закрываем ссесию во избежания ошибок и проблем
        await self.session.close()
