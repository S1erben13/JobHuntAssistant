"""Фильтры и балл вакансии. Не зависят от источника."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .config import Config, Profile
from .models import Vacancy

_WORD = r"[0-9a-zа-яё]"


def has_keyword(text: str, keyword: str) -> bool:
    """Ключевое слово должно начинаться с начала слова: «сет» найдётся в «сеть», но не в «посетитель».
    Латинские слова ищутся целиком, чтобы «pos» не находился в «position»."""
    tail = rf"(?!{_WORD})" if keyword.isascii() else ""
    return re.search(rf"(?<!{_WORD}){re.escape(keyword)}{tail}", text) is not None


def _norm(s: str) -> str:
    return s.lower().replace("ё", "е").strip()


def passes_filters(v: Vacancy, profile: Profile, cfg: Config) -> bool:
    name = v.name.lower()
    if any(w in name for w in cfg.exclude_title):
        return False
    if v.field_work:
        return False
    if v.experience_min_years is not None and v.experience_min_years > profile.max_experience_years:
        return False
    if profile.remote:
        if v.remote is not True:
            return False
    else:
        if v.remote is True:
            return False
        if profile.metro:
            allowed = {_norm(m) for m in profile.metro}
            if not any(_norm(m) in allowed for m in v.metro):
                return False
    return True


def _salary_net(v: Vacancy) -> int | None:
    """Зарплата на руки в рублях (грубо: до вычета × 0.87)."""
    if (v.salary_currency or "RUR").upper() not in ("RUR", "RUB"):
        return None
    value = v.salary_from or v.salary_to
    if not value:
        return None
    return int(value * 0.87) if v.salary_gross else int(value)


def score(v: Vacancy, profile: Profile, cfg: Config, now: datetime | None = None) -> int:
    w = cfg.scoring
    now = now or datetime.now(timezone.utc)
    total, reasons = 0, []

    name = v.name.lower()
    title_hits = [k for k in profile.keywords if has_keyword(name, k)]
    if title_hits:
        total += w.get("title_keyword", 3) * len(title_hits)
        reasons.append("в названии: " + ", ".join(title_hits))

    text = v.text
    text_hits = [k for k in profile.keywords if k not in title_hits and has_keyword(text, k)]
    if text_hits:
        total += min(w.get("text_keyword", 1) * len(text_hits), w.get("text_keyword_cap", 8))
        reasons.append("в описании: " + ", ".join(text_hits))

    penalties = [p for p in cfg.penalty_words if p in text]
    if penalties:
        total += w.get("penalty_word", -5) * len(penalties)
        reasons.append("разъезды?: " + ", ".join(penalties))

    salary = _salary_net(v)
    if salary is not None and profile.min_salary:
        if salary >= profile.min_salary:
            total += w.get("salary_ok", 2)
            reasons.append("зарплата ок")
        else:
            total += w.get("salary_low", -3)
            reasons.append("зарплата ниже минимума")

    if v.has_test:
        total += w.get("has_test", -1)
        reasons.append("тестовое")

    if v.published_at and (now - v.published_at).days <= w.get("fresh_days", 3):
        total += w.get("fresh", 1)
        reasons.append("свежая")

    v.score, v.reasons = total, reasons
    return total


def best_profile(v: Vacancy, cfg: Config) -> bool:
    """Подбирает лучший профиль для вакансии. False — не подошла ни под один."""
    best: tuple[int, str, list[str]] | None = None
    for p in cfg.profiles:
        if not passes_filters(v, p, cfg):
            continue
        s = score(v, p, cfg)
        if best is None or s > best[0]:
            best = (s, p.name, v.reasons)
    if best is None:
        return False
    v.score, v.profile, v.reasons = best
    return True
