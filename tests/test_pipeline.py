from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from jobhunt.config import load_config
from jobhunt.export import Tracker, export
from jobhunt.pipeline import collect, select_top
from jobhunt.vacancy import from_api, passes_filters, score, strip_html

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)


def item(id_, name, *, formats=("REMOTE",), salary=None, desc_req="", metro=None, days_ago=1, has_test=False):
    return {
        "id": str(id_),
        "name": name,
        "employer": {"name": "ООО Ромашка"},
        "alternate_url": f"https://hh.ru/vacancy/{id_}",
        "published_at": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "salary": salary,
        "work_format": [{"id": f} for f in formats],
        "experience": {"name": "От 1 года до 3 лет"},
        "has_test": has_test,
        "address": {"raw": "СПб", "metro_stations": [{"station_name": m} for m in (metro or [])]},
        "snippet": {"requirement": desc_req, "responsibility": None},
    }


@pytest.fixture
def cfg():
    return load_config(ROOT / "profiles.yaml")


def prof(cfg, name):
    return next(p for p in cfg.profiles if p.name == name)


def test_strip_html():
    assert strip_html("<p>Опыт с <highlighttext>R-keeper</highlighttext></p><ul><li>касса</li></ul>") == "Опыт с R-keeper\n- касса"


def test_engineer_not_excluded_but_developer_is(cfg):
    p = prof(cfg, "helpdesk")
    assert passes_filters(from_api(item(1, "Инженер технической поддержки")), p, cfg)
    assert not passes_filters(from_api(item(2, "Python-разработчик")), p, cfg)
    assert not passes_filters(from_api(item(3, "Выездной инженер")), p, cfg)


def test_field_work_and_format_filter(cfg):
    p = prof(cfg, "pos")
    assert not passes_filters(from_api(item(1, "Специалист поддержки", formats=("REMOTE", "FIELD_WORK"))), p, cfg)
    assert not passes_filters(from_api(item(2, "Специалист поддержки", formats=("ON_SITE",))), p, cfg)


def test_office_metro_filter(cfg):
    p = prof(cfg, "office")
    ok = from_api(item(1, "Специалист поддержки", formats=("ON_SITE",), metro=["Черная речка"]))
    far = from_api(item(2, "Специалист поддержки", formats=("ON_SITE",), metro=["Девяткино"]))
    assert passes_filters(ok, p, cfg)
    assert not passes_filters(far, p, cfg)


def test_score_prefers_relevant(cfg):
    p = prof(cfg, "pos")
    good = from_api(item(1, "Специалист поддержки R-keeper", salary={"from": 90000, "currency": "RUR", "gross": False},
                         desc_req="Знание ККТ АТОЛ, эквайринг"))
    bad = from_api(item(2, "Специалист поддержки", salary={"from": 40000, "currency": "RUR", "gross": False},
                        desc_req="Выезды на объекты, командировки", days_ago=10, has_test=True))
    assert score(good, p, cfg, NOW) > 5
    assert score(bad, p, cfg, NOW) < 0
    assert any("разъезды" in r for r in bad.reasons)


class FakeClient:
    def __init__(self, items):
        self.items = items

    def search(self, profile, query):
        return self.items

    def details(self, vid):
        return {"description": "<p>Работа с R-keeper и iiko</p>", "key_skills": [{"name": "R-keeper"}]}


def test_pipeline_and_export(cfg, tmp_path):
    cfg.profiles = [prof(cfg, "pos")]
    client = FakeClient([item(i, f"Специалист поддержки кассового ПО {i}") for i in range(30)] + [item(99, "Senior DevOps")])
    candidates = collect(client, cfg, skip_ids={"0"})
    assert {v.id for v in candidates} == {str(i) for i in range(1, 30)}

    top = select_top(client, cfg, candidates, 15)
    assert len(top) == 15
    assert "R-keeper" in top[0].key_skills

    tracker = Tracker(tmp_path / "tracker.csv")
    day_dir = export(top, tmp_path, tracker, date(2026, 11, 3))
    md = (day_dir / "vacancies.md").read_text(encoding="utf-8")
    assert md.startswith("# Вакансии на 2026-11-03 — 15 шт.")
    assert (tmp_path / "prompt.md").exists()

    reread = Tracker(tmp_path / "tracker.csv")
    assert len(reread.rows) == 15 and reread.rows[0]["статус"] == "новая"
    assert reread.add(top, date(2026, 11, 4)) == 0  # повторно не добавляет


def test_office_limit(cfg):
    cfg.profiles = [prof(cfg, "office")]
    client = FakeClient([item(i, "Специалист технической поддержки", formats=("ON_SITE",), metro=["Петроградская"]) for i in range(5)])
    top = select_top(client, cfg, collect(client, cfg, set()), 15)
    assert len(top) == 2


def test_keyword_word_start():
    from jobhunt.vacancy import has_keyword
    assert has_keyword("настройка сети", "сет")
    assert not has_keyword("встреча посетителей", "сет")
    assert has_keyword("pos-терминалы", "pos")
    assert not has_keyword("open position", "pos")
    assert has_keyword("знание 1с", "1с")


def test_cashier_excluded(cfg):
    assert not passes_filters(from_api(item(1, "Кассир-бариста")), prof(cfg, "pos"), cfg)
