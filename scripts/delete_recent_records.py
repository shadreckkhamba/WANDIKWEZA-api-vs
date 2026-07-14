#!/usr/bin/env python3
"""Delete the most recent N records for a specific date."""
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
        description="Delete the most recent N records for a specific date."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument(
        "--date",
        required=True,
        help="Date to delete from (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--count",
        type=int,
        required=True,
        help="Number of most recent records to delete.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = resolve_config_path(args.config)
    db_uri = load_db_uri(config_path)
    engine = create_engine(db_uri)

    delete_query = text("""
        DELETE FROM patient_stay_times
        WHERE id IN (
            SELECT id FROM (
                SELECT id
                FROM patient_stay_times
                WHERE DATE(arrival_time) = :date
                ORDER BY created_at DESC
                LIMIT :count
            ) as subquery
        )
    """)

    with engine.begin() as conn:
        result = conn.execute(delete_query, {"date": args.date, "count": args.count})
        deleted_count = result.rowcount

    print(f"✅ Deleted {deleted_count} most recent records for {args.date}")


if __name__ == "__main__":
    main()
