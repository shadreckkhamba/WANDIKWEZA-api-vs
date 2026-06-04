#!/usr/bin/env python3
"""
Script to ensure each month has a maximum of 100 patient stay time records.
Keeps the most recent records and removes excess ones.
"""
import argparse
from datetime import datetime
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
        description="Limit patient stay time records to 100 per month."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument(
        "--max-per-month",
        type=int,
        default=100,
        help="Maximum records to keep per month (default: 100).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = resolve_config_path(args.config)
    db_uri = load_db_uri(config_path)
    engine = create_engine(db_uri)

    # Get count per month
    count_query = text("""
        SELECT 
            DATE_FORMAT(arrival_time, '%Y-%m') as month,
            COUNT(*) as count
        FROM patient_stay_times
        GROUP BY DATE_FORMAT(arrival_time, '%Y-%m')
        ORDER BY month DESC
    """)

    with engine.connect() as conn:
        result = conn.execute(count_query)
        months_data = result.fetchall()

    print("\nCurrent records per month:")
    print("-" * 40)
    total_to_delete = 0
    for month, count in months_data:
        excess = max(0, count - args.max_per_month)
        status = f"❌ {excess} excess" if excess > 0 else "✅ OK"
        print(f"{month}: {count} records {status}")
        total_to_delete += excess

    if total_to_delete == 0:
        print("\n✅ All months are within the limit!")
        return

    print(f"\nTotal records to delete: {total_to_delete}")

    if args.dry_run:
        print("\n🔍 Dry run mode - no records will be deleted")
        return

    # Delete excess records, keeping the most recent ones
    delete_query = text("""
        DELETE FROM patient_stay_times
        WHERE id IN (
            SELECT id FROM (
                SELECT 
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY DATE_FORMAT(arrival_time, '%Y-%m')
                        ORDER BY arrival_time DESC
                    ) as row_num
                FROM patient_stay_times
            ) as ranked
            WHERE row_num > :max_per_month
        )
    """)

    with engine.begin() as conn:
        result = conn.execute(delete_query, {"max_per_month": args.max_per_month})
        deleted_count = result.rowcount

    print(f"\n✅ Deleted {deleted_count} excess records")
    print(f"Each month now has a maximum of {args.max_per_month} records")


if __name__ == "__main__":
    main()
