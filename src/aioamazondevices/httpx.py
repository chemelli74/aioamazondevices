"""Wrapper around httpx.Response to mimic aiohttp.ClientResponse."""

import types
from http.cookies import SimpleCookie
from typing import Any, Self, cast

from httpx import AsyncClient, Cookies, Response
from httpx._types import RequestData


def convert_httpx_cookies_to_simplecookie(httpx_cookies: Cookies) -> SimpleCookie:
    """Convert an httpx.Cookies object to a single SimpleCookie."""
    simple_cookie = SimpleCookie()

    for name, value in httpx_cookies.items():
        simple_cookie[name] = value

    return simple_cookie


class HttpxClientResponseWrapper:
    """aiohttp-like Wrapper for httpx.Response."""

    def __init__(self, response: Response) -> None:
        """Init wrapper."""
        self._response = response

        # Basic aiohttp-like attributes
        self.status = response.status_code
        self.headers = response.headers
        self.url = response.url
        self.reason = response.reason_phrase
        self.cookies = convert_httpx_cookies_to_simplecookie(response.cookies)
        self.ok = response.is_success

        # Aiohttp compatibility
        self.content_type = response.headers.get("Content-Type", "")
        self.real_url = str(response.url)
        self.request_info = types.SimpleNamespace(
            real_url=self.url,
            method=response.request.method,
            headers=response.request.headers,
        )

        # History (aiohttp returns redirects as history)
        self.history = (
            [HttpxClientResponseWrapper(r) for r in response.history]
            if response.history
            else []
        )

    async def text(self, encoding: str | None = None) -> str:
        """Text."""
        # httpx auto-decodes
        if encoding:
            return cast("str", self._response.content.decode(encoding))
        return cast("str", self._response.text)

    async def json(self) -> Any:  # noqa: ANN401
        """Json."""
        return self._response.json()

    async def read(self) -> bytes:
        """Read."""
        return cast("bytes", self._response.content)

    async def release(self) -> None:
        """Release."""
        # No-op: aiohttp requires this, httpx does not

    def raise_for_status(self) -> Response:
        """Raise for status."""
        return self._response.raise_for_status()

    def __repr__(self) -> str:
        """Repr."""
        return f"<HttpxClientResponseWrapper [{self.status} {self.reason}]>"

    async def __aenter__(self) -> Self:
        """Aenter."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Aexit."""
        await self.release()


class HttpxClientSession:
    """aiohttp-like Wrapper for httpx.AsyncClient."""

    def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
        """Init session."""
        # Allow passing any httpx.AsyncClient init kwargs (e.g., headers, cookies)
        self._client = AsyncClient(**kwargs)

    @property
    def closed(self) -> bool:
        """Indicates whether the underlying client session is closed."""
        return cast("bool", self._client.is_closed)

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str | int | float] | None = None,
        data: Any = None,  # noqa: ANN401
        json: Any = None,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> HttpxClientResponseWrapper:
        """Make a generic request method for any HTTP verb."""
        response = await self._client.request(
            method=method.upper(),
            url=url,
            params=params,
            data=data,
            json=json,
            **kwargs,
        )
        return HttpxClientResponseWrapper(response)

    async def get(self, url: str, **kwargs: Any) -> HttpxClientResponseWrapper:  # noqa: ANN401
        """Get."""
        response = await self._client.get(url, **kwargs)
        return HttpxClientResponseWrapper(response)

    async def post(
        self,
        url: str,
        data: RequestData | None = None,
        json: Any = None,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> HttpxClientResponseWrapper:
        """Post."""
        response = await self._client.post(url, data=data, json=json, **kwargs)
        return HttpxClientResponseWrapper(response)

    async def close(self) -> None:
        """Close."""
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        """AEnter."""
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """AExit."""
        await self._client.__aexit__(exc_type, exc_val, exc_tb)
