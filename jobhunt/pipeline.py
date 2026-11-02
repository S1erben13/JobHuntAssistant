"""Сбор → фильтр → скоринг → детали для лучших → топ-N."""

from __future__ import annotations

import logging

import requests

from .config import Config
from .hh_client import HHClient
from .vacancy import Vacancy, add_details, from_api, passes_filters, score

logger = logging.getLogger(__name__)


def collect(client: HHClient, cfg: Config, skip_ids: set[str]) -> list[Vacancy]:
    """Все подходящие под фильтры вакансии по всем профилям, без дублей и без уже известных."""
    found: dict[str, Vacancy] = {}
    for profile in cfg.profiles:
        for query in profile.queries:
            try:
                items = client.search(profile, query)
            except requests.RequestException as e:
                logger.error("[%s] «%s»: ошибка запроса: %s", profile.name, query, e)
                continue
            for item in items:
                vid = str(item["id"])
                if vid in skip_ids:
                    continue
                v = from_api(item, profile.name)
                if not passes_filters(v, profile, cfg):
                    continue
                score(v, profile, cfg)
                # одна вакансия могла найтись в нескольких профилях — оставляем лучший балл
                if vid not in found or v.score > found[vid].score:
                    found[vid] = v
    return list(found.values())


def select_top(client: HHClient, cfg: Config, candidates: list[Vacancy], top: int) -> list[Vacancy]:
    """Подгружает описания для лучших кандидатов, пересчитывает балл и возвращает топ."""
    profiles = {p.name: p for p in cfg.profiles}
    candidates.sort(key=lambda v: (v.score, v.published_at), reverse=True)
    pool = candidates[: top * 3]
    for v in pool:
        try:
            add_details(v, client.details(v.id))
        except requests.RequestException as e:
            logger.warning("Не удалось получить описание %s: %s", v.id, e)
        score(v, profiles[v.profile], cfg)
    pool.sort(key=lambda v: (v.score, v.published_at), reverse=True)

    result: list[Vacancy] = []
    per_profile: dict[str, int] = {}
    for v in pool:
        limit = profiles[v.profile].max_results
        if limit is not None and per_profile.get(v.profile, 0) >= limit:
            continue
        result.append(v)
        per_profile[v.profile] = per_profile.get(v.profile, 0) + 1
        if len(result) >= top:
            break
    return result
