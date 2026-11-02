"""Приведение ответа hh.ru к плоской структуре, фильтры и скоринг."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import Config, Profile


@dataclass
class Vacancy:
    id: str
    name: str
    employer: str
    url: str
    published_at: datetime
    salary_from: int | None
    salary_to: int | None
    salary_currency: str | None
    salary_gross: bool | None
    work_formats: list[str]
    experience: str
    has_test: bool
    metro: list[str]
    address: str
    snippet: str
    description: str = ""
    key_skills: list[str] = field(default_factory=list)
    profile: str = ""
    score: int = 0
    reasons: list[str] = field(default_factory=list)

    @property
    def salary_text(self) -> str:
        if self.salary_from is None and self.salary_to is None:
            return "не указана"
        parts = []
        if self.salary_from:
            parts.append(f"от {self.salary_from:,}".replace(",", " "))
        if self.salary_to:
            parts.append(f"до {self.salary_to:,}".replace(",", " "))
        cur = {"RUR": "₽", "RUB": "₽"}.get(self.salary_currency or "", self.salary_currency or "")
        tax = "" if self.salary_gross is None else (" до вычета" if self.salary_gross else " на руки")
        return f"{' '.join(parts)} {cur}{tax}".strip()

    @property
    def text(self) -> str:
        return " ".join([self.snippet, self.description, " ".join(self.key_skills)]).lower()


_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = re.sub(r"<\s*(br|/p|/li|/h\d)\s*/?>", "\n", raw, flags=re.I)
    text = re.sub(r"<\s*li[^>]*>", "- ", text, flags=re.I)
    text = html.unescape(_TAG_RE.sub("", text))
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def from_api(item: dict[str, Any], profile: str = "") -> Vacancy:
    salary = item.get("salary_range") or item.get("salary") or {}
    snippet = item.get("snippet") or {}
    address = item.get("address") or {}
    metro = [s.get("station_name", "") for s in address.get("metro_stations") or []]
    if not metro and address.get("metro"):
        metro = [address["metro"].get("station_name", "")]
    return Vacancy(
        id=str(item["id"]),
        name=item.get("name", ""),
        employer=(item.get("employer") or {}).get("name", ""),
        url=item.get("alternate_url") or f"https://hh.ru/vacancy/{item['id']}",
        published_at=datetime.strptime(item["published_at"], "%Y-%m-%dT%H:%M:%S%z"),
        salary_from=salary.get("from"),
        salary_to=salary.get("to"),
        salary_currency=salary.get("currency"),
        salary_gross=salary.get("gross"),
        work_formats=[w.get("id", "") for w in item.get("work_format") or []],
        experience=(item.get("experience") or {}).get("name", ""),
        has_test=bool(item.get("has_test")),
        metro=[m for m in metro if m],
        address=address.get("raw") or "",
        snippet=strip_html(" ".join(filter(None, [snippet.get("requirement"), snippet.get("responsibility")]))),
        profile=profile,
    )


def add_details(v: Vacancy, details: dict[str, Any]) -> None:
    v.description = strip_html(details.get("description"))
    v.key_skills = [s.get("name", "") for s in details.get("key_skills") or []]


def passes_filters(v: Vacancy, profile: Profile, cfg: Config) -> bool:
    name = v.name.lower()
    if any(w in name for w in cfg.exclude_title):
        return False
    if "FIELD_WORK" in v.work_formats:
        return False
    if v.work_formats and not set(v.work_formats) & set(profile.work_format):
        return False
    if profile.metro:
        allowed = {m.lower().replace("ё", "е") for m in profile.metro}
        if not any(m.lower().replace("ё", "е") in allowed for m in v.metro):
            return False
    return True


def _norm_salary(v: Vacancy) -> int | None:
    """Зарплата на руки в рублях (грубо: gross * 0.87)."""
    if v.salary_currency not in (None, "RUR", "RUB"):
        return None
    value = v.salary_from or v.salary_to
    if value is None:
        return None
    return int(value * 0.87) if v.salary_gross else int(value)


def score(v: Vacancy, profile: Profile, cfg: Config, now: datetime | None = None) -> int:
    w = cfg.scoring
    now = now or datetime.now(timezone.utc)
    total, reasons = 0, []

    name = v.name.lower()
    title_hits = [k for k in profile.keywords if k in name]
    if title_hits:
        total += w.get("title_keyword", 3) * len(title_hits)
        reasons.append("в названии: " + ", ".join(title_hits))

    text = v.text
    text_hits = [k for k in profile.keywords if k in text and k not in title_hits]
    if text_hits:
        total += min(w.get("text_keyword", 1) * len(text_hits), w.get("text_keyword_cap", 8))
        reasons.append("в описании: " + ", ".join(text_hits))

    penalties = [p for p in cfg.penalty_words if p in text]
    if penalties:
        total += w.get("penalty_word", -5) * len(penalties)
        reasons.append("разъезды?: " + ", ".join(penalties))

    salary = _norm_salary(v)
    if salary is not None:
        if salary >= profile.min_salary:
            total += w.get("salary_ok", 2)
            reasons.append("зарплата ок")
        else:
            total += w.get("salary_low", -3)
            reasons.append("зарплата ниже минимума")

    if v.has_test:
        total += w.get("has_test", -1)
        reasons.append("тестовое")

    if (now - v.published_at).days <= w.get("fresh_days", 3):
        total += w.get("fresh", 1)
        reasons.append("свежая")

    v.score, v.reasons = total, reasons
    return total
