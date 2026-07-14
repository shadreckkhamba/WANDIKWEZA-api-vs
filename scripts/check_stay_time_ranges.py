#!/usr/bin/env python3
"""Check stay time distribution in the database."""
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
        description="Check stay time distribution."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = resolve_config_path(args.config)
    db_uri = load_db_uri(config_path)
    engine = create_engine(db_uri)

    # Check specific range
    query = text("""
        SELECT 
            CASE 
                WHEN difference_hours < 1 THEN '0-1 hours'
                WHEN difference_hours >= 1 AND difference_hours < 2 THEN '1-2 hours'
                WHEN difference_hours >= 2 AND difference_hours < 3 THEN '2-3 hours'
                WHEN difference_hours >= 3 AND difference_hours < 4 THEN '3-4 hours'
                WHEN difference_hours >= 4 AND difference_hours < 5 THEN '4-5 hours'
                WHEN difference_hours >= 5 THEN '5+ hours'
            END as range_group,
            COUNT(*) as count,
            MIN(difference_hours) as min_hours,
            MAX(difference_hours) as max_hours
        FROM patient_stay_times
        GROUP BY range_group
        ORDER BY min_hours
    """)

    with engine.connect() as conn:
        result = conn.execute(query)
        rows = result.fetchall()

    print("\nStay Time Distribution:")
    print("-" * 60)
    total = 0
    for row in rows:
        range_group, count, min_hours, max_hours = row
        total += count
        print(f"{range_group:15s}: {count:5d} patients (min: {min_hours:.2f}h, max: {max_hours:.2f}h)")
    
    print("-" * 60)
    print(f"{'Total':15s}: {total:5d} patients")

    # Check specifically for 4-5 hour range
    check_query = text("""
        SELECT COUNT(*) as count
        FROM patient_stay_times
        WHERE difference_hours >= 4 AND difference_hours < 5
    """)

    with engine.connect() as conn:
        result = conn.execute(check_query)
        count_4_5 = result.fetchone()[0]

    print(f"\n{'4-5 hours range':15s}: {count_4_5} patients")
    
    if count_4_5 == 0:
        print("❌ No stay times in the 4-5 hours range")
    else:
        print("✅ Found stay times in the 4-5 hours range")


if __name__ == "__main__":
    main()
