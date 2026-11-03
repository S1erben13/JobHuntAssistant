"""JobHuntAssistant: собирает вакансии с нескольких площадок и готовит их для нейросети.

Примеры:
    python run.py                          # все готовые источники и профили, топ-15
    python run.py --sources trudvsem       # только один источник
    python run.py --profiles pos helpdesk --top 20
    python run.py --check                  # какие источники готовы и почему остальные пропущены
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from jobhunt.config import default_output_dir, load_config
from jobhunt.export import Tracker, export
from jobhunt.pipeline import collect, select_top
from jobhunt.sources import REGISTRY, build_sources


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Сбор вакансий и выгрузка для нейросети")
    parser.add_argument("--top", type=int, default=int(os.getenv("TOP", 15)), help="сколько вакансий выгрузить")
    parser.add_argument("--profiles", nargs="*", help="профили из profiles.yaml (по умолчанию все)")
    parser.add_argument("--sources", nargs="*", choices=sorted(REGISTRY), help="источники (по умолчанию все готовые)")
    parser.add_argument("--config", default=None, help="файл профилей (по умолчанию profiles.local.yaml или profiles.yaml)")
    parser.add_argument("--out", type=Path, default=None, help="папка выгрузки")
    parser.add_argument("--check", action="store_true", help="только показать готовность источников")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.out:
        os.environ["OUTPUT_DIR"] = str(args.out)
    cfg = load_config(args.config, args.profiles)
    out_dir = default_output_dir()

    sources, skipped = build_sources(cfg.sources, args.sources)
    for name, reason in skipped.items():
        logging.info("Источник %s пропущен: %s", name, reason)
    logging.info("Источники в работе: %s", ", ".join(s.name for s in sources) or "нет")
    if args.check:
        return 0
    if not sources:
        logging.error("Нет ни одного готового источника. См. README, раздел «Источники».")
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    tracker = Tracker(out_dir / "tracker.csv")
    candidates = collect(sources, cfg, skip_ids=tracker.ids)
    logging.info("Новых подходящих вакансий: %d", len(candidates))
    top = select_top(sources, cfg, candidates, args.top)

    day_dir = export(top, out_dir, tracker, date.today())
    for src in sources:
        finish = getattr(src, "finish", None)
        if finish:
            finish()
    logging.info("Готово: %d вакансий в %s", len(top), day_dir)
    logging.info("Трекер откликов: %s", out_dir / "tracker.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
