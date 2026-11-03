"""hh.ru через сохранённые страницы.

С 15.12.2025 hh.ru закрыл API для соискателей, поэтому программа не ходит на hh сама.
Ты открываешь поиск или вакансию в своём браузере, жмёшь Ctrl+S («Веб-страница, только HTML»)
и кладёшь файл в папку hh-inbox. Программа разбирает файлы и переносит их в hh-inbox/processed.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from bs4 import BeautifulSoup

from ..config import Config, Profile, default_output_dir
from ..models import Vacancy, strip_html, years_from_text
from .base import Source

logger = logging.getLogger(__name__)
VACANCY_URL_RE = re.compile(r"hh\.ru/vacancy/(\d+)")


def _remote_flags(text: str) -> tuple[bool | None, bool]:
    t = text.lower()
    field = "разъездн" in t or "выездн" in t
    remote = True if ("удалённо" in t or "удаленно" in t or "удалённая работа" in t or "удаленная работа" in t) else None
    return remote, field


def _iter_dicts(node: Any) -> Iterator[dict]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_dicts(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_dicts(value)


def _from_state(soup: BeautifulSoup) -> list[Vacancy]:
    """Страницы hh содержат JSON-состояние в <template id="HH-Lux-InitialState">."""
    tpl = soup.find("template", id="HH-Lux-InitialState")
    if not tpl or not tpl.string:
        return []
    try:
        state = json.loads(tpl.string)
    except json.JSONDecodeError:
        return []
    found: dict[str, Vacancy] = {}
    for d in _iter_dicts(state):
        vid = d.get("vacancyId")
        if not vid or not isinstance(d.get("name"), str):
            continue
        comp = d.get("compensation") or {}
        company = d.get("company") or {}
        snippet = d.get("snippet") or {}
        pub = (d.get("publicationTime") or {}).get("$") if isinstance(d.get("publicationTime"), dict) else d.get("publicationTime")
        formats = " ".join(str(f.get("workFormatsElement", f)) if isinstance(f, dict) else str(f) for f in d.get("workFormats") or [])
        remote = True if "REMOTE" in formats else None
        metro = [m.get("name", "") for m in ((d.get("address") or {}).get("metroStations") or {}).get("metro", []) if isinstance(m, dict)]
        found[str(vid)] = Vacancy(
            source="hh",
            source_id=str(vid),
            name=d["name"],
            employer=company.get("visibleName") or company.get("name") or "",
            url=f"https://hh.ru/vacancy/{vid}",
            published_at=_parse_dt(pub),
            salary_from=comp.get("from"),
            salary_to=comp.get("to"),
            salary_currency=comp.get("currencyCode") or "RUR",
            salary_gross=comp.get("gross"),
            remote=remote,
            field_work="FIELD_WORK" in formats,
            experience_min_years=years_from_text(str(d.get("workExperience") or "").replace("between", " ").replace("And", " ")) if d.get("workExperience") else None,
            region=(d.get("area") or {}).get("name", "") if isinstance(d.get("area"), dict) else "",
            metro=[m for m in metro if m],
            snippet=strip_html(" ".join(str(snippet.get(k) or "") for k in ("req", "resp", "requirement", "responsibility"))),
        )
    return list(found.values())


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _qa(node: Any, name: str) -> str:
    el = node.select_one(f'[data-qa="{name}"]')
    return el.get_text(" ", strip=True) if el else ""


def _from_vacancy_page(soup: BeautifulSoup, html: str) -> list[Vacancy]:
    title = _qa(soup, "vacancy-title")
    m = VACANCY_URL_RE.search(html)
    desc = soup.select_one('[data-qa="vacancy-description"]')
    if not title or not m or not desc:
        return []
    page_text = soup.get_text(" ", strip=True)
    remote, field = _remote_flags(_qa(soup, "work-formats-text") or page_text)
    salary = _qa(soup, "vacancy-salary")
    return [Vacancy(
        source="hh",
        source_id=m.group(1),
        name=title,
        employer=_qa(soup, "vacancy-company-name"),
        url=f"https://hh.ru/vacancy/{m.group(1)}",
        published_at=None,
        salary_from=_salary_num(salary),
        salary_gross="до вычета" in salary if salary else None,
        remote=remote,
        field_work=field,
        experience_min_years=years_from_text(_qa(soup, "vacancy-experience")),
        experience_text=_qa(soup, "vacancy-experience"),
        metro=[e.get_text(strip=True) for e in soup.select('[data-qa="address-metro-station-name"]')],
        address=_qa(soup, "vacancy-view-raw-address"),
        description=strip_html(str(desc)),
        key_skills=[e.get_text(strip=True) for e in soup.select('[data-qa="skills-element"]')],
    )]


def _salary_num(text: str) -> int | None:
    m = re.search(r"\d[\d\s \xa0]*", text or "")
    return int(re.sub(r"\D", "", m.group())) if m else None


def _from_search_cards(soup: BeautifulSoup) -> list[Vacancy]:
    found: dict[str, Vacancy] = {}
    for link in soup.select('a[data-qa="serp-item__title"], a[href*="hh.ru/vacancy/"]'):
        m = VACANCY_URL_RE.search(link.get("href", ""))
        if not m or m.group(1) in found:
            continue
        card = link.find_parent(attrs={"data-qa": re.compile(r"vacancy-serp__vacancy$")}) or link.find_parent("div")
        card_text = card.get_text(" ", strip=True) if card else ""
        remote, field = _remote_flags(card_text)
        exp = re.search(r"(без опыта|опыт[^·|]{0,20}\d[^·|]{0,10})", card_text, re.I)
        found[m.group(1)] = Vacancy(
            source="hh",
            source_id=m.group(1),
            name=link.get_text(" ", strip=True),
            employer=_qa(card, "vacancy-serp__vacancy-employer") if card else "",
            url=f"https://hh.ru/vacancy/{m.group(1)}",
            published_at=None,
            salary_from=_salary_num(_qa(card, "vacancy-serp__vacancy-compensation")) if card else None,
            remote=remote,
            field_work=field,
            experience_min_years=years_from_text(exp.group(0)) if exp else None,
            metro=[e.get_text(strip=True) for e in card.select('[data-qa="address-metro-station-name"]')] if card else [],
            address=_qa(card, "vacancy-serp__vacancy-address") if card else "",
            snippet=card_text[:1500],
        )
    return [v for v in found.values() if v.name]


def parse_html(html: str) -> list[Vacancy]:
    soup = BeautifulSoup(html, "html.parser")
    return _from_vacancy_page(soup, html) or _from_state(soup) or _from_search_cards(soup)


class HHSavedSource(Source):
    name = "hh"

    def __init__(self, settings: dict[str, Any]):
        super().__init__(settings)
        inbox = self.settings.get("inbox")
        self.inbox = Path(inbox).expanduser() if inbox else default_output_dir() / "hh-inbox"
        self.assume_remote = bool(self.settings.get("assume_remote", True))
        self._cache: list[Vacancy] | None = None
        self._files: list[Path] = []

    def _html_files(self) -> list[Path]:
        if not self.inbox.exists():
            return []
        return sorted(p for p in self.inbox.iterdir() if p.is_file() and p.suffix.lower() in (".html", ".htm"))

    def unavailable_reason(self) -> str | None:
        if not self._html_files():
            return f"в {self.inbox} нет сохранённых страниц hh (.html)"
        return None

    def _load(self) -> list[Vacancy]:
        if self._cache is None:
            self._files = self._html_files()
            result: dict[str, Vacancy] = {}
            for path in self._files:
                items = parse_html(path.read_text(encoding="utf-8", errors="ignore"))
                logger.info("[hh] %s: %d вакансий", path.name, len(items))
                for v in items:
                    if v.remote is None and self.assume_remote:
                        v.remote = True
                    # страница вакансии полнее карточки поиска
                    if v.source_id not in result or len(v.description) > len(result[v.source_id].description):
                        result[v.source_id] = v
            self._cache = list(result.values())
        return self._cache

    def fetch(self, profile: Profile, cfg: Config) -> Iterable[Vacancy]:
        # Страницы уже отфильтрованы поиском на hh: отдаём их всем профилям, лучший выберет скоринг
        return list(self._load())

    def finish(self) -> None:
        done = self.inbox / "processed"
        done.mkdir(exist_ok=True)
        for path in self._files:
            shutil.move(str(path), done / path.name)
