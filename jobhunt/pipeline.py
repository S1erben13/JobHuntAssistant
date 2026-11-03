"""Сбор со всех готовых источников → фильтр и балл → топ-N."""

from __future__ import annotations

import logging
import re

import requests

from .config import Config
from .models import Vacancy
from .scoring import best_profile
from .sources.base import Source

logger = logging.getLogger(__name__)


def _dup_key(v: Vacancy) -> str:
    """Одна и та же вакансия часто есть на нескольких площадках: сравниваем по названию и работодателю."""
    norm = lambda s: re.sub(r"[^0-9a-zа-я]", "", s.lower().replace("ё", "е"))
    return f"{norm(v.name)}|{norm(v.employer)}"


def collect(sources: list[Source], cfg: Config, skip_ids: set[str]) -> list[Vacancy]:
    by_key: dict[str, Vacancy] = {}
    for src in sources:
        seen_in_source: set[str] = set()
        for profile in cfg.profiles:
            try:
                items = list(src.fetch(profile, cfg))
            except requests.RequestException as e:
                logger.error("[%s/%s] ошибка запроса: %s", src.name, profile.name, e)
                continue
            for v in items:
                if v.id in skip_ids or v.id in seen_in_source:
                    continue
                seen_in_source.add(v.id)
                if not best_profile(v, cfg):
                    continue
                key = _dup_key(v)
                old = by_key.get(key)
                if old is None or (v.score, len(v.description)) > (old.score, len(old.description)):
                    by_key[key] = v
    return list(by_key.values())


def select_top(sources: list[Source], cfg: Config, candidates: list[Vacancy], top: int) -> list[Vacancy]:
    profiles = {p.name: p for p in cfg.profiles}
    by_name = {s.name: s for s in sources}
    order = lambda v: (v.score, v.published_at.timestamp() if v.published_at else 0)
    candidates.sort(key=order, reverse=True)
    pool = candidates[: top * 3]
    for v in pool:
        src = by_name.get(v.source)
        if src:
            try:
                src.enrich(v)
            except requests.RequestException as e:
                logger.warning("Не удалось догрузить %s: %s", v.id, e)
        best_profile(v, cfg)
    pool.sort(key=order, reverse=True)

    result: list[Vacancy] = []
    per_profile: dict[str, int] = {}
    for v in pool:
        limit = profiles[v.profile].max_results if v.profile in profiles else None
        if limit is not None and per_profile.get(v.profile, 0) >= limit:
            continue
        result.append(v)
        per_profile[v.profile] = per_profile.get(v.profile, 0) + 1
        if len(result) >= top:
            break
    return result
