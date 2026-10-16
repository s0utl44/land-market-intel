"""Grzeczny klient HTTP: przerwy między zapytaniami, ponawianie przy błędach przejściowych.

Odpowiedź 403 kończy działanie (Blocked). Celowo nie próbujemy obchodzić blokad.
"""
from __future__ import annotations

import os
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

DEFAULT_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"


class Blocked(Exception):
    """Serwis odmówił dostępu (403). Nie ponawiamy."""


class FetchError(Exception):
    pass


@dataclass
class PoliteClient:
    # 4–8 s między zapytaniami: 2026-10-16 Otodom zablokował serwer (403) przy 2–4 s
    min_delay: float = 4.0
    max_delay: float = 8.0
    retries: int = 3
    timeout: float = 40.0
    user_agent: str = field(default_factory=lambda: os.environ.get("LMI_USER_AGENT", DEFAULT_UA))
    requests_made: int = 0
    _last: float = 0.0

    def _wait(self) -> None:
        delay = random.uniform(self.min_delay, self.max_delay)
        elapsed = time.monotonic() - self._last
        if elapsed < delay:
            time.sleep(delay - elapsed)

    def get(self, url: str, headers: dict | None = None) -> str:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            self._wait()
            req = urllib.request.Request(
                url, headers={"User-Agent": self.user_agent, "Accept-Language": "pl-PL,pl;q=0.9", **(headers or {})}
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8", "replace")
                self._last = time.monotonic()
                self.requests_made += 1
                return body
            except urllib.error.HTTPError as exc:
                self._last = time.monotonic()
                self.requests_made += 1
                if exc.code == 403:
                    raise Blocked(f"403 dla {url}") from exc
                if exc.code == 404:
                    raise FetchError(f"404 dla {url}") from exc
                last_error = exc  # 429 / 5xx: ponów z dłuższą przerwą
            except (urllib.error.URLError, TimeoutError) as exc:
                self._last = time.monotonic()
                last_error = exc
            time.sleep(min(60, 5 * 2**attempt))
        raise FetchError(f"Nie udało się pobrać {url}: {last_error}")
