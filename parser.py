import aiohttp
import asyncio
import json
import aiofiles
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
from datetime import datetime
from tqdm.asyncio import tqdm


@dataclass
class Skin:
    id: int
    name: str
    price: float
    unlock_at: Optional[str]
    item_class_id: str
    created_at: str
    item_float: Optional[str] = None
    name_tag: Optional[str] = None
    item_paint_index: Optional[str] = None
    item_paint_seed: Optional[str] = None
    stickers: Optional[List[Dict]] = None
    gems: Optional[List[Dict]] = None
    styles: Optional[Dict] = None
    item_asset_id: Optional[str] = None
    game_id: Optional[int] = None


class SkinsParser:
    BASE_URL = "https://api.lis-skins.com/v1/market/search"
    DEFAULT_GAME = "csgo"
    DEFAULT_PER_PAGE = 100
    DEFAULT_HEADERS = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    MAX_PAGES = 300  # Защита от бесконечного цикла
    DUPLICATE_LIMIT = 5  # Максимальное количество дубликатов перед остановкой

    def __init__(self, api_token: str, output_file: str = "skins.json"):
        if not api_token:
            raise ValueError("API token is required")

        self.output_file = output_file
        self.api_token = api_token
        self.session = None
        self.skins = []
        self.current_page = 0
        self.progress_bar = None
        self.seen_ids = set()  # Для отслеживания дубликатов
        self.duplicate_counter = 0  # Счетчик дубликатов подряд

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={**self.DEFAULT_HEADERS, "Authorization": f"Bearer {self.api_token}"}
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
        if self.progress_bar:
            self.progress_bar.close()

    async def _make_request(self, params: Dict[str, Any]) -> Dict:
        async with self.session.get(self.BASE_URL, params=params) as response:
            response.raise_for_status()
            return await response.json()

    async def fetch_page(self, cursor: Optional[str] = None) -> Dict:
        params = {
            "game": self.DEFAULT_GAME,
            "per_page": self.DEFAULT_PER_PAGE,
        }
        if cursor:
            params["cursor"] = cursor

        return await self._make_request(params)

    @staticmethod
    def process_skin_data(skin_data: Dict) -> Skin:
        return Skin(
            id=skin_data["id"],
            name=skin_data["name"],
            price=skin_data["price"],
            unlock_at=skin_data["unlock_at"],
            item_class_id=skin_data["item_class_id"],
            created_at=skin_data["created_at"],
            item_float=skin_data.get("item_float"),
            name_tag=skin_data.get("name_tag"),
            item_paint_index=skin_data.get("item_paint_index"),
            item_paint_seed=skin_data.get("item_paint_seed"),
            stickers=skin_data.get("stickers"),
            gems=skin_data.get("gems"),
            styles=skin_data.get("styles"),
            item_asset_id=skin_data.get("item_asset_id"),
            game_id=skin_data.get("game_id"),
        )

    async def save_to_json_async(self):
        skins_data = [asdict(skin) for skin in self.skins]
        async with aiofiles.open(self.output_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(skins_data, ensure_ascii=False, indent=4))

    async def parse_all_skins(self):
        cursor = None
        has_more = True
        self.progress_bar = tqdm(desc="Parsing pages", unit="page")

        while has_more and self.current_page < self.MAX_PAGES:
            try:
                data = await self.fetch_page(cursor)
                new_skins = [self.process_skin_data(skin) for skin in data["data"]]
                print(f"{data} \n\n\n {new_skins}")


                # Проверка на дубликаты
                current_duplicates = 0
                for skin in new_skins:
                    if skin.id in self.seen_ids:
                        current_duplicates += 1
                    else:
                        self.seen_ids.add(skin.id)

                if current_duplicates == len(new_skins):
                    self.duplicate_counter += 1
                    if self.duplicate_counter >= self.DUPLICATE_LIMIT:
                        self.progress_bar.write(f"Stopping: too many duplicates ({self.DUPLICATE_LIMIT} times)")
                        break
                else:
                    self.duplicate_counter = 0

                self.skins.extend(new_skins)
                self.current_page += 1

                self.progress_bar.set_description(
                    f"Page {self.current_page} | {len(new_skins)} skins | "
                    f"Dupl: {current_duplicates}/{len(new_skins)}"
                )
                self.progress_bar.update(1)

                await self.save_to_json_async()

                cursor = data.get("meta", {}).get("next_cursor")
                has_more = bool(cursor) and len(new_skins) > 0

                await asyncio.sleep(0.1)

            except aiohttp.ClientError as e:
                self.progress_bar.write(f"Network error: {e}")
                has_more = False
            except Exception as e:
                self.progress_bar.write(f"Unexpected error: {e}")
                has_more = False

    async def run(self):
        start_time = datetime.now()
        print(f"Starting parsing for game: {self.DEFAULT_GAME}")

        try:
            await self.parse_all_skins()

            end_time = datetime.now()
            print(f"\nParsing completed in {end_time - start_time}")
            print(f"Total pages parsed: {self.current_page}")
            print(f"Total unique skins collected: {len(self.seen_ids)}")
            print(f"Results saved to {self.output_file}")
        except Exception as e:
            print(f"\nFailed to complete parsing: {e}")
        finally:
            if self.progress_bar:
                self.progress_bar.close()


async def main():
    API_TOKEN = "cbe0870e-dfda-4a34-8bb7-fd25d2f30ce5"

    if not API_TOKEN or API_TOKEN == "your_api_token_here":
        raise ValueError("Please provide a valid API token")

    async with SkinsParser(api_token=API_TOKEN) as parser:
        await parser.run()


if __name__ == "__main__":
    asyncio.run(main())