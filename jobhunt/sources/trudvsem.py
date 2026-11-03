"""«Работа России» (trudvsem.ru): открытый API, ключ не нужен.

Документация: https://trudvsem.ru/opendata/api
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from ..config import Config, Profile
from ..models import Vacancy, strip_html
from .base import HttpSource

logger = logging.getLogger(__name__)
API = "http://opendata.trudvsem.ru/api/v1/vacancies"
REGION_CODES = {"spb": "7800000000000", "moscow": "7700000000000"}
# Удалёнка указана в employment: «Дистанционная (удаленная) работа»; в schedule её нет
REMOTE_MARKERS = ("удален", "удалён", "дистанц")


def parse(raw: dict[str, Any]) -> Vacancy:
    v = raw.get("vacancy", raw)
    req = v.get("requirement") or {}
    addresses = (v.get("addresses") or {}).get("address") or []
    fmt = " ".join(str(v.get(k) or "") for k in ("schedule", "employment")).lower()
    created = v.get("creation-date")
    published = datetime.strptime(created[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc) if created else None
    exp = req.get("experience")
    return Vacancy(
        source="trudvsem",
        source_id=str(v.get("id")),
        name=v.get("job-name", ""),
        employer=(v.get("company") or {}).get("name", ""),
        url=v.get("vac_url") or "",
        published_at=published,
        salary_from=v.get("salary_min") or None,
        salary_to=v.get("salary_max") or None,
        salary_currency="RUR",
        remote=any(m in fmt for m in REMOTE_MARKERS),
        field_work="вахт" in fmt or "разъезд" in fmt,
        experience_min_years=int(exp) if isinstance(exp, (int, float)) or (isinstance(exp, str) and exp.isdigit()) else None,
        experience_text=f"от {exp} лет" if exp not in (None, "") else "",
        region=(v.get("region") or {}).get("name", ""),
        address="; ".join(a.get("location", "") for a in addresses if a.get("location")),
        description=strip_html("\n".join(filter(None, [v.get("duty"), v.get("requirements")]))),
        key_skills=[str(x) for x in v.get("skills") or []],
    )


class TrudvsemSource(HttpSource):
    name = "trudvsem"

    def fetch(self, profile: Profile, cfg: Config) -> Iterable[Vacancy]:
        url = API
        if profile.region in REGION_CODES:
            url = f"{API}/region/{REGION_CODES[profile.region]}"
        since = (datetime.now(timezone.utc) - timedelta(days=profile.period_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for query in profile.queries:
            got = 0
            page = 0
            while got < profile.per_query:
                limit = min(100, profile.per_query - got)
                # offset — номер страницы, а не сдвиг
                data = self.get_json(url, params={"text": query, "offset": page, "limit": limit, "modifiedFrom": since})
                items = ((data.get("results") or {}).get("vacancies")) or []
                for item in items:
                    yield parse(item)
                got += len(items)
                page += 1
                if len(items) < limit:
                    break
            logger.info("[trudvsem/%s] «%s»: %d", profile.name, query, got)
