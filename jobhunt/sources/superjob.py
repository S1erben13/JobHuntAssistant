"""SuperJob: API для соискателей, нужен бесплатный ключ приложения (SUPERJOB_API_KEY).

Как получить ключ — в README, раздел «Источники».
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from ..config import Config, Profile
from ..models import Vacancy, strip_html
from .base import HttpSource

logger = logging.getLogger(__name__)
API = "https://api.superjob.ru/2.0/vacancies/"
TOWNS = {"spb": 14, "moscow": 4}
PLACE_REMOTE, PLACE_FIELD = 2, 3
# experience id: 1 — без опыта, 2 — от 1 года, 3 — от 3 лет, 4 — от 6 лет
EXPERIENCE_YEARS = {1: 0, 2: 1, 3: 3, 4: 6}


def parse(item: dict[str, Any]) -> Vacancy:
    place = (item.get("place_of_work") or {}).get("id")
    exp = item.get("experience") or {}
    published = item.get("date_published")
    return Vacancy(
        source="superjob",
        source_id=str(item["id"]),
        name=item.get("profession", ""),
        employer=item.get("firm_name", ""),
        url=item.get("link", ""),
        published_at=datetime.fromtimestamp(published, tz=timezone.utc) if published else None,
        salary_from=item.get("payment_from") or None,
        salary_to=item.get("payment_to") or None,
        salary_currency=(item.get("currency") or "rub").upper().replace("RUB", "RUR"),
        remote=place == PLACE_REMOTE,
        field_work=place == PLACE_FIELD,
        experience_min_years=EXPERIENCE_YEARS.get(exp.get("id")),
        experience_text=exp.get("title", ""),
        region=(item.get("town") or {}).get("title", ""),
        metro=[m.get("title", "") for m in item.get("metro") or [] if m.get("title")],
        address=item.get("address") or "",
        description=strip_html(item.get("vacancyRichText") or "\n".join(filter(None, [item.get("candidat"), item.get("work")]))),
    )


class SuperJobSource(HttpSource):
    name = "superjob"

    def unavailable_reason(self) -> str | None:
        if not os.getenv("SUPERJOB_API_KEY"):
            return "нет SUPERJOB_API_KEY в .env"
        return None

    def fetch(self, profile: Profile, cfg: Config) -> Iterable[Vacancy]:
        headers = {"X-Api-App-Id": os.environ["SUPERJOB_API_KEY"]}
        since = int((datetime.now(timezone.utc) - timedelta(days=profile.period_days)).timestamp())
        for query in profile.queries:
            params: dict[str, Any] = {"keyword": query, "count": min(100, profile.per_query), "date_published_from": since,
                                      "order_field": "date"}
            if profile.region in TOWNS:
                params["town"] = TOWNS[profile.region]
            if profile.remote:
                params["place_of_work"] = PLACE_REMOTE
            got, page = 0, 0
            while got < profile.per_query:
                data = self.get_json(API, params={**params, "page": page}, headers=headers)
                items = data.get("objects") or []
                for item in items:
                    yield parse(item)
                got += len(items)
                page += 1
                if not data.get("more") or not items:
                    break
            logger.info("[superjob/%s] «%s»: %d", profile.name, query, got)
