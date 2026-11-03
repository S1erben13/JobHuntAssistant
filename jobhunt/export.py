"""Выгрузка вакансий: Markdown для нейросети, CSV и трекер откликов."""

from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path

from .models import Vacancy

TRACKER_FIELDS = ["id", "источник", "дата", "профиль", "балл", "вакансия", "работодатель", "зарплата", "ссылка", "статус", "заметка"]
STATUS_NEW = "новая"

PROMPT = """# Как пользоваться

1. Открой нейросеть (Claude, ChatGPT и т.п.).
2. Приложи своё резюме и файл vacancies.md из папки за нужный день.
3. Вставь текст ниже.

---

Ниже моё резюме и список вакансий. Для каждой вакансии напиши сопроводительное письмо:
- 5–7 предложений, без шаблонных фраз вроде «идеально подхожу»;
- 2–3 конкретных пункта из моего опыта, которые закрывают требования вакансии;
- не приписывай мне навыки, которых нет в резюме; если требования не закрываю, честно скажи, что быстро разберусь, и чем это подкреплено;
- в конце одна строка с контактами.

Перед каждым письмом напиши номер и название вакансии. Если вакансия мне явно не подходит, напиши об этом одной строкой вместо письма.
"""


def write_markdown(vacancies: list[Vacancy], path: Path, day: date) -> None:
    """Повторный запуск в тот же день дописывает новые вакансии в конец, а не затирает файл."""
    start = 1
    if path.exists():
        start = len(re.findall(r"^## \d+\. ", path.read_text(encoding="utf-8"), flags=re.M)) + 1
        lines = ["", f"# Дополнение {datetime.now():%H:%M} — {len(vacancies)} шт.", ""]
    else:
        lines = [f"# Вакансии на {day.isoformat()} — {len(vacancies)} шт.", ""]
    for i, v in enumerate(vacancies, start):
        lines += [
            f"## {i}. {v.name} — {v.employer}",
            "",
            f"- Ссылка: {v.url}",
            f"- Источник: {v.source}",
            f"- Профиль: {v.profile}",
            f"- Зарплата: {v.salary_text}",
            f"- Формат: {v.format_text}",
            f"- Опыт: {v.experience_text or 'не указан'}",
        ]
        if v.metro or v.address:
            lines.append(f"- Адрес: {v.address or ''} {('(м. ' + ', '.join(v.metro) + ')') if v.metro else ''}".rstrip())
        if v.key_skills:
            lines.append(f"- Ключевые навыки: {', '.join(v.key_skills)}")
        lines += [f"- Балл: {v.score} ({'; '.join(v.reasons)})", "", "### Описание", "", v.description or v.snippet, ""]
    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_csv(vacancies: list[Vacancy], path: Path) -> None:
    # utf-8-sig, чтобы Excel на Windows открыл кириллицу без танцев
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig" if new_file else "utf-8") as f:
        w = csv.writer(f, delimiter=";")
        if new_file:
            w.writerow(["балл", "источник", "профиль", "вакансия", "работодатель", "зарплата", "ссылка", "почему"])
        for v in vacancies:
            w.writerow([v.score, v.source, v.profile, v.name, v.employer, v.salary_text, v.url, "; ".join(v.reasons)])


class Tracker:
    """tracker.csv: одна строка на вакансию. Статус правишь руками: новая / откликнулся / отказ / приглашение / пропуск."""

    def __init__(self, path: Path):
        self.path = path
        self.rows: list[dict[str, str]] = []
        if path.exists():
            with path.open(encoding="utf-8-sig", newline="") as f:
                self.rows = list(csv.DictReader(f, delimiter=";"))

    @property
    def ids(self) -> set[str]:
        return {r["id"] for r in self.rows}

    def add(self, vacancies: list[Vacancy], day: date) -> int:
        known = self.ids
        added = 0
        for v in vacancies:
            if v.id in known:
                continue
            self.rows.append({
                "id": v.id, "источник": v.source, "дата": day.isoformat(), "профиль": v.profile, "балл": str(v.score),
                "вакансия": v.name, "работодатель": v.employer, "зарплата": v.salary_text,
                "ссылка": v.url, "статус": STATUS_NEW, "заметка": "",
            })
            added += 1
        return added

    def save(self) -> None:
        with self.path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=TRACKER_FIELDS, delimiter=";", extrasaction="ignore")
            w.writeheader()
            w.writerows(self.rows)


def export(vacancies: list[Vacancy], out_dir: Path, tracker: Tracker, day: date) -> Path:
    day_dir = out_dir / day.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    if not vacancies and (day_dir / "vacancies.md").exists():
        return day_dir  # новых нет — сегодняшнюю выгрузку не трогаем
    write_markdown(vacancies, day_dir / "vacancies.md", day)
    write_csv(vacancies, day_dir / "vacancies.csv")
    prompt = out_dir / "prompt.md"
    if not prompt.exists():
        prompt.write_text(PROMPT, encoding="utf-8")
    tracker.add(vacancies, day)
    tracker.save()
    return day_dir
