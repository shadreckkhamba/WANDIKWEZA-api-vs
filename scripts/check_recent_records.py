#!/usr/bin/env python3
"""Check the most recent records and their running averages."""
import argparse
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
        description="Check recent records and running averages."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument(
        "--date",
        required=True,
        help="Date to check (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of recent records to show (default: 5).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = resolve_config_path(args.config)
    db_uri = load_db_uri(config_path)
    engine = create_engine(db_uri)

    # Get all records for the date ordered by creation time
    query = text("""
        SELECT 
            id,
            patient_id,
            arrival_time,
            difference_hours,
            created_at
        FROM patient_stay_times
        WHERE DATE(arrival_time) = :date
        ORDER BY created_at DESC
        LIMIT :limit
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {"date": args.date, "limit": args.limit})
        records = result.fetchall()

    if not records:
        print(f"No records found for {args.date}")
        return

    # Get running averages by excluding records one by one
    print(f"\nMost Recent Records for {args.date}:")
    print("-" * 100)
    print(f"{'#':<4} {'Patient ID':<12} {'Stay Time':<12} {'Created At':<20} {'Running Avg':<15} {'Change':<10}")
    print("-" * 100)

    for i, record in enumerate(records):
        record_id, patient_id, arrival_time, stay_hours, created_at = record
        
        # Calculate average excluding records newer than this one
        avg_query = text("""
            SELECT AVG(difference_hours) as avg_hours, COUNT(*) as count
            FROM patient_stay_times
            WHERE DATE(arrival_time) = :date
            AND created_at <= :created_at
        """)
        
        with engine.connect() as conn:
            avg_result = conn.execute(avg_query, {"date": args.date, "created_at": created_at})
            avg_row = avg_result.fetchone()
            avg_hours, count = avg_row
        
        # Format stay time
        stay_h = int(stay_hours)
        stay_m = int((stay_hours - stay_h) * 60)
        stay_str = f"{stay_h}h {stay_m:02d}m"
        
        # Format running average
        avg_h = int(avg_hours)
        avg_m = int((avg_hours - avg_h) * 60)
        avg_str = f"{avg_h}h {avg_m:02d}m ({count})"
        
        # Calculate change from previous
        change = ""
        if i < len(records) - 1:
            # Get previous average (next in list since we're going backwards)
            prev_query = text("""
                SELECT AVG(difference_hours) as avg_hours
                FROM patient_stay_times
                WHERE DATE(arrival_time) = :date
                AND created_at <= :created_at
            """)
            
            with engine.connect() as conn:
                prev_result = conn.execute(prev_query, {"date": args.date, "created_at": records[i+1][4]})
                prev_avg = prev_result.fetchone()[0]
            
            diff = avg_hours - prev_avg
            pct = (diff / prev_avg) * 100 if prev_avg > 0 else 0
            if diff > 0:
                change = f"↑ {pct:+.1f}%"
            elif diff < 0:
                change = f"↓ {pct:+.1f}%"
            else:
                change = "→ 0.0%"
        
        print(f"{i+1:<4} {patient_id:<12} {stay_str:<12} {str(created_at):<20} {avg_str:<15} {change:<10}")

    print("-" * 100)


if __name__ == "__main__":
    main()
