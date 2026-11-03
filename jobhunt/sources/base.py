"""Общий интерфейс источника вакансий."""

from __future__ import annotations

import logging
import time
from typing import Any, Iterable

import requests

from ..config import Config, Profile
from ..models import Vacancy

logger = logging.getLogger(__name__)
USER_AGENT = "JobHuntAssistant/3.0 (+https://github.com/S1erben13/JobHuntAssistant)"


class Source:
    """Источник умеет: сказать, готов ли он к работе, и отдать вакансии по профилю."""

    name = "base"

    def __init__(self, settings: dict[str, Any]):
        self.settings = settings or {}

    def unavailable_reason(self) -> str | None:
        """None — источник готов. Строка — почему пропущен (нет ключа, пустая папка и т.п.)."""
        return None

    def fetch(self, profile: Profile, cfg: Config) -> Iterable[Vacancy]:
        raise NotImplementedError

    def enrich(self, v: Vacancy) -> None:
        """Догрузить полное описание, если источник это умеет."""


class HttpSource(Source):
    delay = 0.3

    def __init__(self, settings: dict[str, Any], session: requests.Session | None = None):
        super().__init__(settings)
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)

    def get_json(self, url: str, params: Any = None, headers: dict[str, str] | None = None, retries: int = 3) -> Any:
        for attempt in range(1, retries + 1):
            resp = self.session.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                wait = 2 ** attempt
                logger.warning("%s ответил %s, повтор через %s с", self.name, resp.status_code, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            time.sleep(self.delay)
            return resp.json()
        raise RuntimeError("unreachable")
