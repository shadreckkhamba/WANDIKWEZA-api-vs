#!/usr/bin/env python3
"""Modify the most recent N records to have a specific stay time."""
import argparse
from datetime import timedelta
from pathlib import Path

import yaml
from sqlalchemy import create_engine, text


DEFAULT_CONFIG_PATH = Path("config/dev_config.yaml")
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent


def resolve_config_path(config_arg: str) -> Path:
    path = Path(config_arg).expanduser()
    if path.is_absolute():
        candidate_paths = [path]
    else:
        candidate_paths = [
            Path.cwd() / path,
            PROJECT_ROOT / path,
        ]

    for candidate in candidate_paths:
        if candidate.exists():
            return candidate

    tried = ", ".join(str(candidate) for candidate in candidate_paths)
    raise FileNotFoundError(
        f"Could not find config file '{config_arg}'. Tried: {tried}"
    )


def load_db_uri(config_path: Path) -> str:
    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    db_uri = data["database"]["db_uri"]
    if not db_uri:
        raise ValueError("database.db_uri is empty")
    return db_uri


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Modify the most recent N records to have a specific stay time."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument(
        "--date",
        required=True,
        help="Date to modify (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--count",
        type=int,
        required=True,
        help="Number of most recent records to modify.",
    )
    parser.add_argument(
        "--minutes",
        type=int,
        required=True,
        help="Stay time in minutes.",
    )
    return parser.parse_args()


def format_duration(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def main() -> None:
    args = parse_args()
    config_path = resolve_config_path(args.config)
    db_uri = load_db_uri(config_path)
    engine = create_engine(db_uri)

    stay_seconds = args.minutes * 60
    stay_hours = args.minutes / 60.0
    difference = format_duration(stay_seconds)

    # Get the IDs of the most recent records
    select_query = text("""
        SELECT id, arrival_time
        FROM patient_stay_times
        WHERE DATE(arrival_time) = :date
        ORDER BY created_at DESC
        LIMIT :count
    """)

    with engine.connect() as conn:
        result = conn.execute(select_query, {"date": args.date, "count": args.count})
        records = result.fetchall()

    if not records:
        print(f"No records found for {args.date}")
        return

    print(f"Modifying {len(records)} records to {args.minutes} minutes stay time...")

    # Update each record
    update_query = text("""
        UPDATE patient_stay_times
        SET 
            departure_time = DATE_ADD(arrival_time, INTERVAL :seconds SECOND),
            difference = :difference,
            difference_hours = :difference_hours
        WHERE id = :id
    """)

    with engine.begin() as conn:
        for record_id, arrival_time in records:
            conn.execute(update_query, {
                "id": record_id,
                "seconds": stay_seconds,
                "difference": difference,
                "difference_hours": stay_hours
            })

    print(f"✅ Modified {len(records)} records to {args.minutes} minutes ({stay_hours:.2f} hours)")


if __name__ == "__main__":
    main()
