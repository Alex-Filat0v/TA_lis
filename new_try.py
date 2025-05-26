import requests
import aiohttp
import asyncio
import json
import aiofiles
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict

from requests import JSONDecodeError

BASE_URL = "https://api.lis-skins.com/v1/market/search"
JSON_URL = "https://lis-skins.com/market_export_json/csgo.json"
DEFAULT_GAME = "csgo"
DEFAULT_PER_PAGE = 200
api_token = "cbe0870e-dfda-4a34-8bb7-fd25d2f30ce5"



async def _make_request(params: Dict[str, Any] = None):
    session = aiohttp.ClientSession(
        headers={"Authorization": f"Bearer {api_token}"}
    )
    async with session.get(JSON_URL, params=params) as response:
        response.raise_for_status()
        return await response.json()



async def save_to_json_async(data):
    async with aiofiles.open("new.json", "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=4))



async def fetch_page(cursor: Optional[str] = None):
    params = {
        "game": DEFAULT_GAME,
        "per_page": DEFAULT_PER_PAGE,
    }
    if cursor:
        params["cursor"] = cursor

    return await _make_request()


async def main():
    cursor = None
    start_time = datetime.now()

    data = await fetch_page(cursor)
    await save_to_json_async(data)

    end_time = datetime.now()
    print(f"\nParsing completed in {end_time - start_time}")
    print(f"\nParsing skins: {len(data)}")




if __name__ == "__main__":
    asyncio.run(main())
    #new_skins = [process_skin_data(skin) for skin in data["data"]]
    #print(f"{data} \n\n\n {new_skins}")
