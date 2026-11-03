"""Реестр источников. Чтобы добавить новый — унаследуй Source и впиши класс сюда."""

from __future__ import annotations

from typing import Any

from .base import Source
from .hh_saved import HHSavedSource
from .superjob import SuperJobSource
from .trudvsem import TrudvsemSource

REGISTRY: dict[str, type[Source]] = {
    "trudvsem": TrudvsemSource,
    "superjob": SuperJobSource,
    "hh": HHSavedSource,
}


def build_sources(settings: dict[str, dict[str, Any]], only: list[str] | None = None) -> tuple[list[Source], dict[str, str]]:
    """Возвращает готовые источники и причины, по которым остальные пропущены."""
    ready: list[Source] = []
    skipped: dict[str, str] = {}
    for name, cls in REGISTRY.items():
        conf = settings.get(name) or {}
        if only and name not in only:
            continue
        if conf.get("enabled", True) is False:
            skipped[name] = "выключен в profiles.yaml"
            continue
        src = cls(conf)
        reason = src.unavailable_reason()
        if reason:
            skipped[name] = reason
        else:
            ready.append(src)
    return ready, skipped
