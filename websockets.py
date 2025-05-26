import asyncio
import aiohttp
import json
import requests
from datetime import datetime
import logging
from typing import Dict, Any, Optional

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('LisSkinsParser')


class LisSkinsWebSocketClient:
    """
    Полностью соответствует документации LIS-Skins WebSocket API.
    Реализует подключение к Centrifugo и обработку событий скинов.
    """

    def __init__(self, api_key: str, telegram_bot_token: str, telegram_chat_id: str):
        """
        Инициализация клиента.

        :param api_key: API ключ с https://lis-skins.com/profile/api
        """
        self.api_key = api_key
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.ws_url = "wss://ws.lis-skins.com/connection/websocket"
        self.token_url = "https://api.lis-skins.com/v1/user/get-ws-token"
        self.skins_channel = "public:obtained-skins"

        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.is_connected = False

    async def get_websocket_token(self) -> str:
        """
        Получение токена для WebSocket (точно как в документации).

        :return: WebSocket токен
        :raises: Exception при ошибке
        """
        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            async with self.session.get(self.token_url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['data']['token']
                elif resp.status == 403:
                    raise Exception("Unauthorized: Invalid API key")
                else:
                    raise Exception(f"Unexpected status code {resp.status}")
        except Exception as e:
            logger.error(f"Error getting WS token: {str(e)}")
            raise

    async def connect(self):
        """Установка соединения и подписка на канал (как в Node.js примере)."""
        try:
            # Инициализация сессии
            self.session = aiohttp.ClientSession()

            # Получаем токен
            token = await self.get_websocket_token()

            # Подключаемся к WebSocket
            self.ws = await self.session.ws_connect(
                self.ws_url,
                protocols=["json"],
                headers={"User-Agent": "LisSkinsParser/1.0"}
            )

            # Отправляем сообщение connect (как в Centrifuge)
            await self._send_ws_message({
                "id": 1,
                "method": "connect",
                "params": {
                    "token": token
                }
            })

            # Подписываемся на канал скинов
            await self._send_ws_message({
                "id": 2,
                "method": "subscribe",
                "params": {
                    "channel": self.skins_channel
                }
            })

            self.is_connected = True
            logger.info("Successfully connected and subscribed to skins channel")

        except Exception as e:
            logger.error(f"Connection failed: {str(e)}")
            self.is_connected = False
            raise

    async def _send_ws_message(self, message: Dict[str, Any]):
        """Отправка сообщения через WebSocket."""
        if self.ws and not self.ws.closed:
            await self.ws.send_str(json.dumps(message))

    async def listen(self):
        """
        Прослушивание событий скинов.
        Обрабатывает все типы событий из документации:
        - obtained_skin_added
        - obtained_skin_deleted
        - obtained_skin_price_changed
        """
        if not self.ws:
            raise RuntimeError("WebSocket is not connected")

        async for msg in self.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await self._handle_message(msg.data)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"WebSocket error: {self.ws.exception()}")
                break
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                logger.info("WebSocket connection closed")
                break

    async def _handle_message(self, message: str):
        """
        Обработка входящих сообщений.
        Реализует логику из примера publication в документации.
        """
        try:
            data = json.loads(message)

            # Пропускаем технические сообщения Centrifugo
            if not data.get('result'):
                return

            # Обрабатываем только сообщения из нужного канала
            print(data)
            if data['result'].get('channel') == self.skins_channel:
                event_data = data['result']['data']
                await self._process_skin_event(event_data)

        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON: {message}")
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")

    async def send_telegram_message(self, text: str, parse_mode: str = "Markdown"):
        """
        Отправляет сообщение в Телеграм-чат TELEGRAM_CHAT_ID, используя TELEGRAM_BOT_TOKEN.
        """
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("Телеграм токен или чат-айди не заданы!")
            return

        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"Ошибка при отправке сообщения: {e}")


    async def _process_skin_event(self, event: Dict[str, Any]):
        """
        Обработка события скина.
        Формат данных полностью соответствует документации.
        """
        event_type = event.get('event')
        skin_data = event.get('data', {})

        if not skin_data:
            return

        # Добавляем timestamp к данным
        processed_data = {
            **skin_data,
            "event": event_type,
            "timestamp": datetime.now().isoformat()
        }

        # Выводим в консоль (как в Node.js примере)
        print(json.dumps(processed_data, indent=2, ensure_ascii=False))

        # Отправляем в чат тг
        await self.send_telegram_message(processed_data["item_name"])

        # Сохраняем в файл
        await self._save_to_file(processed_data)

        # Логируем тип события
        logger.info(f"Received {event_type} event")

    async def _save_to_file(self, data: Dict[str, Any]):
        """
        Сохранение данных в JSON файл.
        Формат соответствует примеру из документации.
        """
        filename = "lis_skins_events.json"

        try:
            # Читаем существующие данные
            try:
                with open(filename, 'r') as f:
                    existing_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                existing_data = []

            # Добавляем новые данные
            existing_data.append(data)

            # Сохраняем обратно
            with open(filename, 'w') as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Error saving data: {str(e)}")

    async def run(self):
        """Основной цикл работы с автоматическим переподключением."""
        while True:
            try:
                if not self.is_connected:
                    await self.connect()

                await self.listen()

            except Exception as e:
                logger.error(f"Error: {str(e)}. Reconnecting in 5 seconds...")
                self.is_connected = False
                await asyncio.sleep(5)

            finally:
                if not self.is_connected and self.session:
                    await self.session.close()
                    self.session = None

    async def close(self):
        """Корректное закрытие соединений."""
        if self.ws and not self.ws.closed:
            await self.ws.close()
        if self.session and not self.session.closed:
            await self.session.close()
        self.is_connected = False


async def main():
    # Вставьте ваш API ключ с https://lis-skins.com/profile/api
    API_KEY = "cbe0870e-dfda-4a34-8bb7-fd25d2f30ce5"
    TELEGRAM_BOT_TOKEN = "7462393143:AAHOrdvhRh1aQtLw25IWqrsTNCNQjPRhs2o"
    TELEGRAM_CHAT_ID = "-1002681217614"

    client = LisSkinsWebSocketClient(API_KEY, telegram_bot_token=TELEGRAM_BOT_TOKEN, telegram_chat_id=TELEGRAM_CHAT_ID)

    try:
        await client.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await client.close()
        logger.info("Client stopped")


if __name__ == "__main__":
    asyncio.run(main())
