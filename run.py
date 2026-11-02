"""JobHuntAssistant: собирает подходящие вакансии с hh.ru и готовит их для нейросети.

Пример:
    python run.py                     # все профили, топ-15, в ~/Documents/JobHunt
    python run.py --top 20 --profiles pos helpdesk
    python run.py --out D:/JobHunt
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from jobhunt.config import default_output_dir, load_config
from jobhunt.export import Tracker, export
from jobhunt.hh_client import HHClient
from jobhunt.pipeline import collect, select_top


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Поиск вакансий на hh.ru и выгрузка для нейросети")
    parser.add_argument("--top", type=int, default=int(os.getenv("TOP", 15)), help="сколько вакансий выгрузить")
    parser.add_argument("--profiles", nargs="*", help="какие профили из profiles.yaml (по умолчанию все)")
    parser.add_argument("--config", default="profiles.yaml")
    parser.add_argument("--out", type=Path, default=None, help="папка выгрузки")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(args.config, args.profiles)
    out_dir = (args.out or default_output_dir()).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    tracker = Tracker(out_dir / "tracker.csv")
    client = HHClient(os.getenv("HH_USER_AGENT", ""))

    candidates = collect(client, cfg, skip_ids=tracker.ids)
    logging.info("Новых подходящих вакансий: %d", len(candidates))
    top = select_top(client, cfg, candidates, args.top)

    day_dir = export(top, out_dir, tracker, date.today())
    logging.info("Готово: %d вакансий в %s", len(top), day_dir)
    logging.info("Трекер откликов: %s", out_dir / "tracker.csv")


if __name__ == "__main__":
    main()
