#!/usr/bin/env python3
"""
Seed patient_stay_times with 46 people per day with stay times between 20 minutes and 1h 30m.
For yesterday and today.
"""
import argparse
import random
from datetime import datetime, timedelta
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
        description="Seed people with 20min-1h30m stay times: 102 for Monday, 121 for Tuesday, 117 for yesterday, 119 for today."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated rows without inserting into the database.",
    )
    return parser.parse_args()


def format_duration(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def generate_rows():
    """Generate records with stay times 20min-1h30m for Monday (57), Tuesday (121), yesterday (46), and today (46)."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    monday = datetime(2026, 4, 27, 0, 0, 0)  # Monday, April 27th, 2026
    tuesday = datetime(2026, 4, 28, 0, 0, 0)  # Tuesday, April 28th, 2026
    
    min_minutes = 20
    max_minutes = 90  # 1 hour 30 minutes
    
    # Define days and their record counts
    days_config = [
        (monday, 102, "Monday, April 27th"),
        (tuesday, 121, "Tuesday, April 28th"),
        (yesterday, 117, "yesterday"),
        (today, 119, "today"),
    ]
    
    rows = []
    
    for base_date, records_per_day, day_name in days_config:
        print(f"Generating {records_per_day} records for {day_name} ({base_date.date()})")
        
        for i in range(records_per_day):
            arrival_time = base_date + timedelta(
                hours=random.randint(6, 20),
                minutes=random.randint(0, 59),
                seconds=random.randint(0, 59),
            )

            stay_minutes = random.randint(min_minutes, max_minutes)
            stay_seconds = stay_minutes * 60 + random.randint(0, 59)
            departure_time = arrival_time + timedelta(seconds=stay_seconds)

            difference = format_duration(stay_seconds)
            difference_hours = round(stay_seconds / 3600.0, 2)

            patient_id = str(40000 + len(rows))
            push_time = arrival_time + timedelta(minutes=random.randint(0, 60))

            rows.append(
                {
                    "patient_id": patient_id,
                    "arrival_time": arrival_time,
                    "departure_time": departure_time,
                    "difference": difference,
                    "difference_hours": difference_hours,
                    "push_time": push_time,
                    "source": "seed",
                    "created_at": datetime.now(),
                    "updated_at": datetime.now(),
                }
            )

    return rows


def main() -> None:
    args = parse_args()
    
    print("\n" + "="*60)
    print("Seeding Short Stay Times (20min - 1h 30m)")
    print("="*60 + "\n")
    
    rows = generate_rows()

    if args.dry_run:
        print(f"\nDry run: generated {len(rows)} rows.")
        print("\nSample records:")
        for row in rows[:3]:
            print(f"  Patient {row['patient_id']}: {row['arrival_time']} -> {row['departure_time']} ({row['difference']})")
        return

    config_path = resolve_config_path(args.config)
    db_uri = load_db_uri(config_path)
    engine = create_engine(db_uri)

    insert_sql = text(
        """
        INSERT INTO patient_stay_times
        (patient_id, arrival_time, departure_time, difference, difference_hours,
         push_time, source, created_at, updated_at)
        VALUES
        (:patient_id, :arrival_time, :departure_time, :difference, :difference_hours,
         :push_time, :source, :created_at, :updated_at)
        """
    )

    with engine.begin() as conn:
        conn.execute(insert_sql, rows)

    print(f"\n✅ Inserted {len(rows)} rows into patient_stay_times.")
    print(f"   - 102 records for Monday, April 27th")
    print(f"   - 121 records for Tuesday, April 28th")
    print(f"   - 117 records for yesterday")
    print(f"   - 119 records for today")
    print(f"   - Stay times: 20 minutes to 1 hour 30 minutes\n")


if __name__ == "__main__":
    main()
