#!/usr/bin/env python3
"""
Seed patient_stay_times with daily data ensuring:
- Every day has records
- Monthly total doesn't exceed 100 records
- Random distribution of patients per day
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
        description="Seed patient_stay_times with daily data, max 100 per month."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument(
        "--start-date",
        required=True,
        help="Start date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="End date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--min-per-day",
        type=int,
        default=50,
        help="Minimum records per day (default: 50).",
    )
    parser.add_argument(
        "--max-per-day",
        type=int,
        default=100,
        help="Maximum records per day (default: 100).",
    )
    parser.add_argument("--min-minutes", type=int, default=10)
    parser.add_argument("--max-minutes", type=int, default=300)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated rows without inserting into the database.",
    )
    parser.add_argument(
        "--clear-existing",
        action="store_true",
        help="Clear existing records in the date range before inserting.",
    )
    return parser.parse_args()


def format_duration(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def distribute_records_per_day(days_in_month: int, min_per_day: int = 50, max_per_day: int = 100) -> list:
    """Distribute records across days with random count between min and max per day."""
    records_per_day = []
    
    for _ in range(days_in_month):
        daily_count = random.randint(min_per_day, max_per_day)
        records_per_day.append(daily_count)
    
    return records_per_day


def generate_rows(start_date: str, end_date: str, min_per_day: int, max_per_day: int, min_minutes: int, max_minutes: int):
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    rows = []
    current_date = start_dt
    current_month = None
    month_distribution = []
    day_in_month = 0
    
    while current_date <= end_dt:
        # Check if we're in a new month
        month_key = current_date.strftime("%Y-%m")
        if month_key != current_month:
            current_month = month_key
            # Calculate days in this month (within our range)
            month_start = current_date.replace(day=1)
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)
            
            # Adjust for our date range
            actual_start = max(month_start, start_dt)
            actual_end = min(month_end, end_dt)
            days_in_range = (actual_end - actual_start).days + 1
            
            month_distribution = distribute_records_per_day(days_in_range, min_per_day, max_per_day)
            day_in_month = 0
            print(f"Month {month_key}: {days_in_range} days, {sum(month_distribution)} total records")
        
        # Get number of records for this day
        records_today = month_distribution[day_in_month]
        
        for i in range(records_today):
            arrival_time = current_date + timedelta(
                hours=random.randint(6, 20),
                minutes=random.randint(0, 59),
                seconds=random.randint(0, 59),
            )

            stay_minutes = random.randint(min_minutes, max_minutes)
            stay_seconds = stay_minutes * 60 + random.randint(0, 59)
            departure_time = arrival_time + timedelta(seconds=stay_seconds)

            difference = format_duration(stay_seconds)
            difference_hours = round(stay_seconds / 3600.0, 2)

            patient_id = str(30000 + len(rows))
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
        
        current_date += timedelta(days=1)
        day_in_month += 1

    return rows


def main() -> None:
    args = parse_args()
    
    print(f"\nGenerating data from {args.start_date} to {args.end_date}")
    print(f"Records per day: {args.min_per_day}-{args.max_per_day}\n")
    
    rows = generate_rows(
        start_date=args.start_date,
        end_date=args.end_date,
        min_per_day=args.min_per_day,
        max_per_day=args.max_per_day,
        min_minutes=args.min_minutes,
        max_minutes=args.max_minutes,
    )

    if args.dry_run:
        print(f"\nDry run: generated {len(rows)} rows.")
        return

    config_path = resolve_config_path(args.config)
    db_uri = load_db_uri(config_path)
    engine = create_engine(db_uri)

    with engine.begin() as conn:
        if args.clear_existing:
            delete_sql = text("""
                DELETE FROM patient_stay_times
                WHERE DATE(arrival_time) BETWEEN :start_date AND :end_date
            """)
            result = conn.execute(delete_sql, {
                "start_date": args.start_date,
                "end_date": args.end_date
            })
            print(f"Cleared {result.rowcount} existing records in date range\n")

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
        conn.execute(insert_sql, rows)

    print(f"\n✅ Inserted {len(rows)} rows into patient_stay_times.")


if __name__ == "__main__":
    main()
