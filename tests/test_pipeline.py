import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from jobhunt.config import load_config
from jobhunt.export import Tracker, export
from jobhunt.models import Vacancy, strip_html, years_from_text
from jobhunt.pipeline import collect, select_top
from jobhunt.scoring import best_profile, has_keyword, passes_filters, score
from jobhunt.sources import build_sources
from jobhunt.sources import hh_saved, superjob, trudvsem

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)


@pytest.fixture
def cfg():
    return load_config(ROOT / "profiles.yaml")


def prof(cfg, name):
    return next(p for p in cfg.profiles if p.name == name)


def vac(i, name, **kw):
    base = dict(source="test", source_id=str(i), name=name, employer="ООО Ромашка", url=f"https://example.com/{i}",
                published_at=NOW - timedelta(days=1), remote=True)
    base.update(kw)
    return Vacancy(**base)


# --- общие функции ---

def test_strip_html_and_years():
    assert strip_html("<p>Опыт с <b>R-keeper</b></p><ul><li>касса</li></ul>") == "Опыт с R-keeper\n- касса"
    assert years_from_text("Нет опыта") == 0
    assert years_from_text("От 1 года до 3 лет") == 1


def test_keyword_word_start():
    assert has_keyword("настройка сети", "сет")
    assert not has_keyword("встреча посетителей", "сет")
    assert has_keyword("pos-терминалы", "pos")
    assert not has_keyword("open position", "pos")


def test_filters(cfg):
    helpdesk, office = prof(cfg, "helpdesk"), prof(cfg, "office")
    assert passes_filters(vac(1, "Инженер технической поддержки"), helpdesk, cfg)
    assert not passes_filters(vac(2, "Python-разработчик"), helpdesk, cfg)
    assert not passes_filters(vac(3, "Кассир-бариста"), helpdesk, cfg)
    assert not passes_filters(vac(4, "Специалист поддержки", field_work=True), helpdesk, cfg)
    assert not passes_filters(vac(5, "Специалист поддержки", experience_min_years=5), helpdesk, cfg)
    assert not passes_filters(vac(6, "Специалист поддержки", remote=None), helpdesk, cfg)
    assert passes_filters(vac(7, "Специалист поддержки", remote=False, metro=["Черная речка"]), office, cfg)
    assert not passes_filters(vac(8, "Специалист поддержки", remote=False, metro=["Девяткино"]), office, cfg)
    # без метро — по расстоянию от Петроградской
    assert passes_filters(vac(9, "Специалист поддержки", remote=False, lat=59.9756, lon=30.3045), office, cfg)  # ул. Академика Павлова
    assert not passes_filters(vac(10, "Специалист поддержки", remote=False, lat=59.8335, lon=30.3497), office, cfg)  # Звёздная
    assert not passes_filters(vac(11, "Специалист поддержки", remote=False), office, cfg)


def test_score_prefers_relevant(cfg):
    p = prof(cfg, "pos")
    good = vac(1, "Специалист поддержки R-keeper", salary_from=90000, salary_gross=False, snippet="ККТ АТОЛ, эквайринг")
    bad = vac(2, "Специалист поддержки", salary_from=40000, snippet="Выезды на объекты, командировки",
              published_at=NOW - timedelta(days=10), has_test=True)
    assert score(good, p, cfg, NOW) > 5
    assert score(bad, p, cfg, NOW) < 0


# --- источники ---

def test_trudvsem_parse(cfg):
    items = json.loads((FIX / "trudvsem.json").read_text(encoding="utf-8"))["results"]["vacancies"]
    v1, v2 = [trudvsem.parse(i) for i in items]
    assert v1.id == "trudvsem:aaaa-1" and v1.remote is True and v1.experience_min_years == 1
    assert v1.salary_from == 90000 and "R-keeper" in v1.description
    assert best_profile(v1, cfg) and v1.profile == "pos"
    assert v2.remote is False and not best_profile(v2, cfg)


def test_superjob_parse(cfg, monkeypatch):
    items = json.loads((FIX / "superjob.json").read_text(encoding="utf-8"))["objects"]
    v1, v2 = [superjob.parse(i) for i in items]
    assert v1.remote is True and v1.experience_min_years == 1 and "Trassir" in v1.description
    assert best_profile(v1, cfg) and v1.profile == "video"
    assert v2.field_work is True and not best_profile(v2, cfg)
    monkeypatch.delenv("SUPERJOB_API_KEY", raising=False)
    assert superjob.SuperJobSource({}).unavailable_reason()


def test_hh_saved_pages(cfg, tmp_path):
    page = hh_saved.parse_html((FIX / "hh_vacancy.html").read_text(encoding="utf-8"))
    assert len(page) == 1
    v = page[0]
    assert v.id == "hh:123456" and v.remote is True and v.salary_from == 90000 and "iiko" in v.key_skills

    cards = hh_saved.parse_html((FIX / "hh_search.html").read_text(encoding="utf-8"))
    by_id = {c.source_id: c for c in cards}
    assert by_id["777"].remote is True and by_id["777"].experience_min_years == 1
    assert by_id["778"].field_work is True

    inbox = tmp_path / "hh-inbox"
    inbox.mkdir()
    for f in ("hh_vacancy.html", "hh_search.html"):
        (inbox / f).write_text((FIX / f).read_text(encoding="utf-8"), encoding="utf-8")
    src = hh_saved.HHSavedSource({"inbox": str(inbox)})
    assert src.unavailable_reason() is None
    found = collect([src], cfg, set())
    assert {v.id for v in found} == {"hh:123456", "hh:777"}
    src.finish()
    assert not list(inbox.glob("*.html")) and len(list((inbox / "processed").glob("*.html"))) == 2


def test_build_sources_skips_unready(cfg, monkeypatch, tmp_path):
    monkeypatch.delenv("SUPERJOB_API_KEY", raising=False)
    cfg.sources["hh"] = {"inbox": str(tmp_path / "empty")}
    ready, skipped = build_sources(cfg.sources)
    assert [s.name for s in ready] == ["trudvsem"]
    assert set(skipped) == {"superjob", "hh"}


# --- пайплайн и выгрузка ---

class FakeSource:
    name = "test"

    def __init__(self, items):
        self.items = items

    def fetch(self, profile, cfg):
        return self.items

    def enrich(self, v):
        v.description = "Работа с R-keeper и iiko"


def test_pipeline_dedup_and_export(cfg, tmp_path):
    cfg.profiles = [prof(cfg, "pos")]
    items = [vac(i, f"Специалист поддержки кассового ПО {i}") for i in range(30)]
    items.append(vac(100, "Специалист поддержки кассового ПО 1", source="other"))  # дубль с другой площадки
    src = FakeSource(items)
    candidates = collect([src], cfg, skip_ids={"test:0"})
    assert len(candidates) == 29

    top = select_top([src], cfg, candidates, 15)
    assert len(top) == 15 and "r-keeper" in " ".join(top[0].reasons)

    tracker = Tracker(tmp_path / "tracker.csv")
    day_dir = export(top, tmp_path, tracker, date(2026, 11, 3))
    md = (day_dir / "vacancies.md").read_text(encoding="utf-8")
    assert md.startswith("# Вакансии на 2026-11-03 — 15 шт.") and "Источник: test" in md
    assert (tmp_path / "prompt.md").exists()
    reread = Tracker(tmp_path / "tracker.csv")
    assert len(reread.rows) == 15 and reread.rows[0]["статус"] == "новая"
    assert reread.add(top, date(2026, 11, 4)) == 0


def test_office_limit(cfg):
    cfg.profiles = [prof(cfg, "office")]
    src = FakeSource([vac(i, "Специалист технической поддержки", employer=f"ООО {i}", remote=False, metro=["Петроградская"]) for i in range(5)])
    assert len(select_top([src], cfg, collect([src], cfg, set()), 15)) == 2


def test_http_retries_broken_response(monkeypatch):
    import requests
    from jobhunt.sources import base

    class Resp:
        status_code = 200
        def json(self):
            return {"ok": True}
        def raise_for_status(self):
            pass

    class Session:
        headers = {}
        calls = 0
        def get(self, *a, **kw):
            Session.calls += 1
            if Session.calls == 1:
                raise requests.exceptions.ChunkedEncodingError("Response ended prematurely")
            return Resp()

    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    src = base.HttpSource({}, session=Session())
    assert src.get_json("http://x") == {"ok": True}
    assert Session.calls == 2


def test_same_day_rerun_appends(cfg, tmp_path):
    tracker = Tracker(tmp_path / "tracker.csv")
    d = date(2026, 11, 3)
    export([vac(1, "Специалист поддержки 1", profile="pos")], tmp_path, tracker, d)
    export([], tmp_path, tracker, d)
    export([vac(2, "Специалист поддержки 2", profile="pos")], tmp_path, tracker, d)
    md = (tmp_path / "2026-11-03" / "vacancies.md").read_text(encoding="utf-8")
    assert "## 1. Специалист поддержки 1" in md and "## 2. Специалист поддержки 2" in md
    rows = (tmp_path / "2026-11-03" / "vacancies.csv").read_text(encoding="utf-8-sig").strip().splitlines()
    assert len(rows) == 3
