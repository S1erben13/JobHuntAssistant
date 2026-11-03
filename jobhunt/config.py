"""Загрузка профилей и настроек.

Порядок поиска файла профилей: --config, затем profiles.local.yaml (личный, в .gitignore), затем profiles.yaml.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REGIONS = {"russia", "spb", "moscow"}


@dataclass
class Profile:
    name: str
    title: str
    queries: list[str]
    keywords: list[str]
    remote: bool
    region: str
    max_experience_years: int
    min_salary: int
    period_days: int
    per_query: int
    metro: list[str] = field(default_factory=list)
    max_results: int | None = None


@dataclass
class Config:
    profiles: list[Profile]
    exclude_title: list[str]
    penalty_words: list[str]
    scoring: dict[str, Any]
    sources: dict[str, dict[str, Any]]


def resolve_config_path(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit)
    local = Path("profiles.local.yaml")
    return local if local.exists() else Path("profiles.yaml")


def load_config(path: str | Path | None = None, only: list[str] | None = None) -> Config:
    data = yaml.safe_load(resolve_config_path(path).read_text(encoding="utf-8"))
    defaults = data.get("defaults", {})
    profiles = []
    for name, raw in data["profiles"].items():
        if only and name not in only:
            continue
        m = {**defaults, **raw}
        region = m.get("region", "russia")
        if region not in REGIONS:
            raise ValueError(f"Профиль {name}: region должен быть одним из {sorted(REGIONS)}")
        profiles.append(
            Profile(
                name=name,
                title=m.get("title", name),
                queries=list(m["queries"]),
                keywords=[k.lower() for k in m.get("keywords", [])],
                remote=bool(m.get("remote", True)),
                region=region,
                max_experience_years=int(m.get("max_experience_years", 3)),
                min_salary=int(m.get("min_salary", 0)),
                period_days=int(m.get("period_days", 14)),
                per_query=int(m.get("per_query", 100)),
                metro=list(m.get("metro", [])),
                max_results=m.get("max_results"),
            )
        )
    if only:
        unknown = set(only) - {p.name for p in profiles}
        if unknown:
            raise ValueError(f"Неизвестные профили: {', '.join(sorted(unknown))}")
    return Config(
        profiles=profiles,
        exclude_title=[w.lower() for w in data.get("exclude_title", [])],
        penalty_words=[w.lower() for w in data.get("penalty_words", [])],
        scoring=data.get("scoring", {}),
        sources=data.get("sources", {}) or {},
    )


def default_output_dir() -> Path:
    """Папка выгрузки: OUTPUT_DIR из .env или ~/Documents/JobHunt."""
    env = os.getenv("OUTPUT_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / "Documents" / "JobHunt"
