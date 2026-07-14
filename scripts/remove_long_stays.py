#!/usr/bin/env python3
"""
Remove patient stay time records where stay duration exceeds 4 hours.
"""
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
        description="Remove patient records with stay time > 4 hours."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument(
        "--max-hours",
        type=float,
        default=4.0,
        help="Maximum stay hours to keep (default: 4.0).",
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

    # Count records to be deleted
    count_query = text("""
        SELECT COUNT(*) as count
        FROM patient_stay_times
        WHERE difference_hours > :max_hours
    """)

    with engine.connect() as conn:
        result = conn.execute(count_query, {"max_hours": args.max_hours})
        count_to_delete = result.fetchone()[0]

    print(f"\nRecords with stay time > {args.max_hours} hours: {count_to_delete}")

    if count_to_delete == 0:
        print("✅ No records to delete!")
        return

    if args.dry_run:
        print("🔍 Dry run mode - no records will be deleted")
        return

    # Delete records
    delete_query = text("""
        DELETE FROM patient_stay_times
        WHERE difference_hours > :max_hours
    """)

    with engine.begin() as conn:
        result = conn.execute(delete_query, {"max_hours": args.max_hours})
        deleted_count = result.rowcount

    print(f"✅ Deleted {deleted_count} records with stay time > {args.max_hours} hours")


if __name__ == "__main__":
    main()
