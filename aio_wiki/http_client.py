import aiohttp

# Check whether responses can be parsed with beautifulsoup
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

import asyncio
import time


class RateLimiter:
    """A leaky bucket rate limiter.

    Allows up to max_rate / time_period acquisitions before blocking.

    time_period is measured in seconds; the default is 60.

    """

    def __init__(self, max_rate: float, time_period: float = 60) -> None:
        self._max_level = max_rate
        self._rate_per_sec = max_rate / time_period
        self._level = 0.0
        self._last_check = 0.0

    def _leak(self) -> None:
        """Drip out capacity from the bucket."""
        if self._level:
            # drip out enough level for the elapsed time since
            # we last checked
            elapsed = time.time() - self._last_check
            decrement = elapsed * self._rate_per_sec
            self._level = max(self._level - decrement, 0)
        self._last_check = time.time()

    def has_capacity(self, amount: float = 1) -> bool:
        """Check if there is enough space remaining in the bucket"""
        self._leak()
        return self._level + amount <= self._max_level

    async def acquire(self, amount: float = 1) -> None:
        """Acquire space in the bucket.

        If the bucket is full, block until there is space.

        """
        if amount > self._max_level:
            raise ValueError("Can't acquire more than the bucket capacity")

        while not self.has_capacity(amount):
            # wait for the next drip to have left the bucket
            await asyncio.sleep(1 / self._rate_per_sec)

        self._level += amount

    async def __aenter__(self) -> None:
        await self.acquire()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass


class HTTPClient:
    def __init__(self, user_agent: str, headers: dict = None, cookies: dict = None, proxy: str = None, timeout: int = 5,
                 rate_limit: int = None, loop=None):

        self.headers = {'User-Agent': user_agent}
        if headers:
            self.headers.update(headers)
        if not cookies:
            self.cookies = {}
        self.proxy = proxy

        if rate_limit:
            self.bucket = RateLimiter(rate_limit)
        else:
            self.bucket = None

        self.timeout = timeout
        if not loop:
            self.loop = asyncio.get_event_loop()
        else:
            self.loop = loop

    async def get(self, url: str, params: dict = None, headers: dict = None, is_text: bool = False,
                  is_json: bool = False,
                  is_bs4: bool = False):
        if self.bucket:
            async with self.bucket:
                return await self._get(url, params, headers, is_text, is_json, is_bs4)
        else:
            return await self._get(url, params, headers, is_text, is_json, is_bs4)

    async def _get(self, url: str, params: dict = None, headers: dict = None, is_text: bool = False,
                   is_json: bool = False,
                   is_bs4: bool = False):
        if not params:
            params = {}

        if is_bs4 and not BeautifulSoup:
            raise ImportError('Unable to import BeautifulSoup, install beautifulsoup4 to parse response')

        if headers:
            session_headers = self.headers.copy()
            session_headers.update(headers)
        else:
            session_headers = self.headers

        async with aiohttp.ClientSession(cookies=self.cookies, headers=session_headers) as session:
            try:
                async with session.get(url, params=params, timeout=self.timeout, proxy=self.proxy) as resp:
                    resp.raise_for_status()
                    if is_text:
                        return await resp.text()
                    elif is_json:
                        return await resp.json()
                    elif is_bs4:
                        content = await resp.read()
                        return await self.loop.run_in_executor(None, lambda x: BeautifulSoup(x, 'lxml'), content)
                    else:
                        return await resp
            except aiohttp.ClientProxyConnectionError:
                raise
            except aiohttp.ClientConnectorError:
                raise
