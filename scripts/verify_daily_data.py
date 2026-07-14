#!/usr/bin/env python3
"""Verify that every day has patient stay time records."""
import argparse
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
        description="Verify daily patient stay time records."
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = resolve_config_path(args.config)
    db_uri = load_db_uri(config_path)
    engine = create_engine(db_uri)

    query = text("""
        SELECT 
            DATE(arrival_time) as day,
            COUNT(*) as count
        FROM patient_stay_times
        WHERE DATE(arrival_time) BETWEEN :start_date AND :end_date
        GROUP BY DATE(arrival_time)
        ORDER BY day
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {
            "start_date": args.start_date,
            "end_date": args.end_date
        })
        daily_counts = {row[0]: row[1] for row in result.fetchall()}

    # Check every day in range
    start_dt = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(args.end_date, "%Y-%m-%d").date()
    current_date = start_dt
    
    missing_days = []
    current_month = None
    month_total = 0
    
    print("\nDaily patient counts:")
    print("-" * 50)
    
    while current_date <= end_dt:
        month_key = current_date.strftime("%Y-%m")
        if month_key != current_month:
            if current_month:
                print(f"  Month {current_month} total: {month_total}")
                print("-" * 50)
            current_month = month_key
            month_total = 0
        
        count = daily_counts.get(current_date, 0)
        month_total += count
        
        status = "✅" if count > 0 else "❌"
        print(f"{current_date} ({current_date.strftime('%a')}): {count:2d} patients {status}")
        
        if count == 0:
            missing_days.append(current_date)
        
        current_date += timedelta(days=1)
    
    if current_month:
        print(f"  Month {current_month} total: {month_total}")
        print("-" * 50)
    
    if missing_days:
        print(f"\n❌ Found {len(missing_days)} days without data:")
        for day in missing_days:
            print(f"  - {day}")
    else:
        print("\n✅ All days have patient data!")


if __name__ == "__main__":
    main()
