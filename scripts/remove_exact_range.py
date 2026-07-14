#!/usr/bin/env python3
"""Remove patient records within a specific stay time range."""
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


def main() -> None:
    config_path = resolve_config_path(str(DEFAULT_CONFIG_PATH))
    db_uri = load_db_uri(config_path)
    engine = create_engine(db_uri)

    # Delete records with stay time >= 4 hours
    delete_query = text("""
        DELETE FROM patient_stay_times
        WHERE difference_hours >= 4.0
    """)

    with engine.begin() as conn:
        result = conn.execute(delete_query)
        deleted_count = result.rowcount

    print(f"✅ Deleted {deleted_count} records with stay time >= 4.0 hours")


if __name__ == "__main__":
    main()
