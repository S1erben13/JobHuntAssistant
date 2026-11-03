"""Общая модель вакансии для всех источников."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Vacancy:
    source: str                     # trudvsem / superjob / hh
    source_id: str                  # id внутри источника
    name: str
    employer: str
    url: str
    published_at: datetime | None
    salary_from: int | None = None
    salary_to: int | None = None
    salary_currency: str | None = "RUR"
    salary_gross: bool | None = None
    remote: bool | None = None      # None — источник не сообщил
    field_work: bool = False        # разъездной характер
    experience_min_years: int | None = None
    experience_text: str = ""
    has_test: bool = False
    region: str = ""
    metro: list[str] = field(default_factory=list)
    address: str = ""
    snippet: str = ""
    description: str = ""
    key_skills: list[str] = field(default_factory=list)
    profile: str = ""
    score: int = 0
    reasons: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.source}:{self.source_id}"

    @property
    def salary_text(self) -> str:
        if not self.salary_from and not self.salary_to:
            return "не указана"
        parts = []
        if self.salary_from:
            parts.append(f"от {self.salary_from:,}".replace(",", " "))
        if self.salary_to:
            parts.append(f"до {self.salary_to:,}".replace(",", " "))
        cur = {"RUR": "₽", "RUB": "₽", "rub": "₽"}.get(self.salary_currency or "", self.salary_currency or "")
        tax = "" if self.salary_gross is None else (" до вычета" if self.salary_gross else " на руки")
        return f"{' '.join(parts)} {cur}{tax}".strip()

    @property
    def text(self) -> str:
        return " ".join([self.snippet, self.description, " ".join(self.key_skills)]).lower()

    @property
    def format_text(self) -> str:
        if self.field_work:
            return "разъездная"
        return {True: "удалённо", False: "офис/гибрид", None: "не указан"}[self.remote]


_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = re.sub(r"<\s*(br|/p|/li|/h\d|/div)\s*/?>", "\n", raw, flags=re.I)
    text = re.sub(r"<\s*li[^>]*>", "- ", text, flags=re.I)
    text = html.unescape(_TAG_RE.sub("", text))
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def years_from_text(text: str | None) -> int | None:
    """«От 1 года до 3 лет» → 1, «Нет опыта» → 0, «Более 6 лет» → 6."""
    if not text:
        return None
    t = text.lower()
    if "нет опыта" in t or "без опыта" in t or "не требуется" in t:
        return 0
    m = re.search(r"\d+", t)
    return int(m.group()) if m else None
