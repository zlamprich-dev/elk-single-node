from __future__ import annotations

import base64
import json
from pathlib import Path
import ssl
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from .errors import ElkctlError


class HttpClient:
    """Internal HTTPS client with explicit CA trust and no outbound proxy."""

    def __init__(self, ca_file: Path, *, username: str | None = None, password: str = "") -> None:
        context = ssl.create_default_context(cafile=str(ca_file))
        self._opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context))
        self._authorization: str | None = None
        if username is not None:
            encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
            self._authorization = f"Basic {encoded}"

    def request(
        self,
        method: str,
        url: str,
        *,
        payload: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: int = 120,
        allow_status: frozenset[int] = frozenset(),
    ) -> tuple[int, bytes]:
        request_headers = dict(headers or {})
        data: bytes | None = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        if self._authorization:
            request_headers["Authorization"] = self._authorization
        request = Request(url, data=data, headers=request_headers, method=method)
        try:
            with self._opener.open(request, timeout=timeout) as response:
                return int(response.status), response.read()
        except HTTPError as exc:
            body = exc.read()
            if exc.code in allow_status:
                return int(exc.code), body
            detail = body.decode("utf-8", errors="replace")[:500]
            raise ElkctlError(f"HTTP {exc.code} from {url}: {detail}") from exc
        except (URLError, TimeoutError, ssl.SSLError) as exc:
            raise ElkctlError(f"HTTPS request failed for {url}: {exc}") from exc

    def json(
        self,
        method: str,
        url: str,
        *,
        payload: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: int = 120,
        allow_status: frozenset[int] = frozenset(),
    ) -> tuple[int, Any]:
        status, body = self.request(
            method,
            url,
            payload=payload,
            headers=headers,
            timeout=timeout,
            allow_status=allow_status,
        )
        if not body:
            return status, None
        try:
            return status, json.loads(body)
        except json.JSONDecodeError as exc:
            raise ElkctlError(f"expected JSON from {url}, received invalid content") from exc

