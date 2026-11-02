"""Загрузка profiles.yaml и настроек окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Profile:
    name: str
    title: str
    queries: list[str]
    keywords: list[str]
    area: int
    work_format: list[str]
    experience: list[str]
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


def load_config(path: str | Path = "profiles.yaml", only: list[str] | None = None) -> Config:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    defaults = data.get("defaults", {})
    profiles = []
    for name, raw in data["profiles"].items():
        if only and name not in only:
            continue
        merged = {**defaults, **raw}
        profiles.append(
            Profile(
                name=name,
                title=merged.get("title", name),
                queries=list(merged["queries"]),
                keywords=[k.lower() for k in merged.get("keywords", [])],
                area=int(merged["area"]),
                work_format=list(merged["work_format"]),
                experience=list(merged["experience"]),
                min_salary=int(merged["min_salary"]),
                period_days=int(merged["period_days"]),
                per_query=int(merged["per_query"]),
                metro=list(merged.get("metro", [])),
                max_results=merged.get("max_results"),
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
    )


def default_output_dir() -> Path:
    """Папка выгрузки: OUTPUT_DIR из .env или ~/Documents/JobHunt."""
    env = os.getenv("OUTPUT_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / "Documents" / "JobHunt"
