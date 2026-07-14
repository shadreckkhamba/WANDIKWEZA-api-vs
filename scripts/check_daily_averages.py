#!/usr/bin/env python3
"""Check daily average stay times."""
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
        description="Check daily average stay times."
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
            COUNT(*) as count,
            AVG(difference_hours) as avg_hours,
            MIN(difference_hours) as min_hours,
            MAX(difference_hours) as max_hours
        FROM patient_stay_times
        WHERE DATE(arrival_time) BETWEEN :start_date AND :end_date
        GROUP BY DATE(arrival_time)
        ORDER BY day DESC
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {
            "start_date": args.start_date,
            "end_date": args.end_date
        })
        rows = result.fetchall()

    print("\nDaily Average Stay Times:")
    print("-" * 80)
    print(f"{'Date':<12} {'Day':<4} {'Count':>6} {'Avg Hours':>10} {'Avg Time':>12} {'Min':>8} {'Max':>8}")
    print("-" * 80)
    
    prev_avg = None
    for row in rows:
        day, count, avg_hours, min_hours, max_hours = row
        
        # Convert to hours and minutes
        avg_h = int(avg_hours)
        avg_m = int((avg_hours - avg_h) * 60)
        
        change = ""
        if prev_avg is not None:
            diff = avg_hours - prev_avg
            pct = (diff / prev_avg) * 100
            if diff > 0:
                change = f"↑ {pct:+.1f}%"
            else:
                change = f"↓ {pct:+.1f}%"
        
        day_name = day.strftime('%a')
        print(f"{day} {day_name:>3} {count:6d} {avg_hours:10.2f} {avg_h:3d}h {avg_m:2d}m {min_hours:8.2f} {max_hours:8.2f} {change}")
        prev_avg = avg_hours

    print("-" * 80)


if __name__ == "__main__":
    main()
