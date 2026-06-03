"""
Async REST-клиент Bybit v5 (public only)
Поддерживает прокси для обхода блокировок CloudFront.
"""
import aiohttp
import asyncio
import os
from config import BYBIT_REST

class BybitClient:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()
        # Считываем прокси из переменной окружения PROXY_URL
        # Формат: http://user:pass@ip:port
        self.proxy = os.getenv("PROXY_URL")

    async def start(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session:
            await self.session.close()

    async def _get(self, path: str, params: dict = None):
        async with self._lock:
            try:
                # Передаем прокси в запрос, если он настроен
                async with self.session.get(
                    f"{BYBIT_REST}{path}", 
                    params=params or {}, 
                    timeout=aiohttp.ClientTimeout(total=15),
                    proxy=self.proxy
                ) as r:
                    if r.status != 200:
                        text = await r.text()
                        print(f"[Bybit] Error {r.status} for {path}: {text[:100]}")
                        return {}
                    try:
                        data = await r.json()
                        return data.get("result", {})
                    except Exception as e:
                        text = await r.text()
                        print(f"[Bybit] JSON error for {path}: {e}. Response: {text[:100]}")
                        return {}
            except Exception as e:
                print(f"[Bybit] Request error for {path}: {e}")
                return {}

    async def get_linear_symbols(self):
        res = await self._get("/v5/market/instruments-info", {"category": "linear"})
        return res.get("list", [])

    async def get_tickers(self):
        res = await self._get("/v5/market/tickers", {"category": "linear"})
        return res.get("list", [])

    async def get_klines(self, symbol: str, interval: str, limit: int = 50):
        res = await self._get("/v5/market/kline", {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        })
        return res.get("list", [])

    async def get_recent_trade(self, symbol: str, limit: int = 100):
        res = await self._get("/v5/market/recent-trade", {
            "category": "linear",
            "symbol": symbol,
            "limit": limit,
        })
        return res.get("list", [])
