"""Минимальный клиент публичного API hh.ru (без авторизации)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .config import Profile

API_URL = "https://api.hh.ru"
logger = logging.getLogger(__name__)


class HHClient:
    def __init__(self, user_agent: str, delay: float = 0.3, session: requests.Session | None = None):
        if not user_agent:
            raise ValueError("Нужен HH_USER_AGENT в .env, например: JobHuntAssistant/2.0 (you@mail.ru)")
        self.session = session or requests.Session()
        # hh.ru требует осмысленный User-Agent с контактом, иначе отвечает 400/403
        self.session.headers.update({"HH-User-Agent": user_agent, "User-Agent": user_agent})
        self.delay = delay

    def _get(self, url: str, params: Any = None, retries: int = 3) -> dict[str, Any]:
        for attempt in range(1, retries + 1):
            resp = self.session.get(url, params=params, timeout=30)
            if resp.status_code in (429, 500, 502, 503) and attempt < retries:
                wait = 2 ** attempt
                logger.warning("hh.ru ответил %s, повтор через %s с", resp.status_code, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            time.sleep(self.delay)
            return resp.json()
        raise RuntimeError("unreachable")

    def search(self, profile: Profile, query: str) -> list[dict[str, Any]]:
        date_from = (datetime.now(timezone.utc) - timedelta(days=profile.period_days)).strftime("%Y-%m-%dT%H:%M:%S%z")
        params: list[tuple[str, Any]] = [
            ("text", query),
            ("area", profile.area),
            ("per_page", min(profile.per_query, 100)),
            ("order_by", "publication_time"),
            ("date_from", date_from),
        ]
        params += [("experience", e) for e in profile.experience]
        params += [("work_format", w) for w in profile.work_format]
        items: list[dict[str, Any]] = []
        page = 0
        while len(items) < profile.per_query:
            data = self._get(f"{API_URL}/vacancies", params=params + [("page", page)])
            items += data.get("items", [])
            page += 1
            if page >= data.get("pages", 0):
                break
        logger.info("[%s] «%s»: %d вакансий", profile.name, query, len(items))
        return items[: profile.per_query]

    def details(self, vacancy_id: str) -> dict[str, Any]:
        return self._get(f"{API_URL}/vacancies/{vacancy_id}")
