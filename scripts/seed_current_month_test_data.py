#!/usr/bin/env python3
"""
Seed January test records into patient_stay_times only.
"""

import argparse
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy.dialects.mysql import insert as mysql_insert

# Ensure project root is importable when running "python3 scripts/<file>.py"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from extensions.extensions import db
from models.patient_stay_time_model import PatientStayTime

START_TIME = time(7, 30)
END_TIME = time(16, 30)
MIN_STAY_MINUTES = 15
MAX_STAY_MINUTES = 240


def parse_args():
    parser = argparse.ArgumentParser(
        description="Seed January test data for patient_stay_times."
    )
    parser.add_argument(
        "--year",
        type=int,
        default=date.today().year,
        help="Year for January records (default: current year).",
    )
    parser.add_argument(
        "--max-per-day",
        type=int,
        default=100,
        help="Maximum number of patients to generate per day (hard-capped at 100).",
    )
    parser.add_argument(
        "--min-per-day",
        type=int,
        default=20,
        help="Minimum number of patients to generate per day.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for reproducible test data.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append without deleting existing January records first.",
    )
    return parser.parse_args()


def january_bounds(year: int):
    january_start = date(year, 1, 1)
    feb_start = date(year, 2, 1)
    return january_start, feb_start


def random_datetime_between(start_dt: datetime, end_dt: datetime) -> datetime:
    seconds = int((end_dt - start_dt).total_seconds())
    return start_dt + timedelta(seconds=random.randint(0, seconds))


def generate_arrival_departure(day: date):
    start_dt = datetime.combine(day, START_TIME)
    end_dt = datetime.combine(day, END_TIME)
    latest_arrival = end_dt - timedelta(minutes=MIN_STAY_MINUTES)

    arrival = random_datetime_between(start_dt, latest_arrival)

    max_stay_for_arrival = min(
        MAX_STAY_MINUTES, int((end_dt - arrival).total_seconds() // 60)
    )
    stay_minutes = random.randint(MIN_STAY_MINUTES, max_stay_for_arrival)
    departure = arrival + timedelta(minutes=stay_minutes)
    return arrival, departure


def replace_existing_january(january_start: date, feb_start: date):
    january_start_dt = datetime.combine(january_start, time.min)
    feb_start_dt = datetime.combine(feb_start, time.min)

    db.session.query(PatientStayTime).filter(
        PatientStayTime.arrival_time >= january_start_dt,
        PatientStayTime.arrival_time < feb_start_dt,
    ).delete(synchronize_session=False)


def seed_january_stay_times(year: int, min_per_day: int, max_per_day: int, append: bool):
    january_start, feb_start = january_bounds(year)

    if not append:
        replace_existing_january(january_start, feb_start)

    stay_count = 0
    generated_days = 0

    patient_id_counter = int(f"{year}010001")

    day_cursor = january_start
    while day_cursor < feb_start:
        daily_total = random.randint(min_per_day, max_per_day)

        for _ in range(daily_total):
            patient_id = patient_id_counter
            patient_id_counter += 1

            arrival, departure = generate_arrival_departure(day_cursor)
            difference = departure - arrival
            difference_hours = round(difference.total_seconds() / 3600, 2)
            push_time = departure + timedelta(minutes=random.randint(0, 30))

            stmt = mysql_insert(PatientStayTime).values(
                patient_id=str(patient_id),
                arrival_time=arrival,
                departure_time=departure,
                difference=str(difference),
                difference_hours=difference_hours,
                daily_average=None,
                percent_change=None,
                push_time=push_time,
                source="test_seed_script",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            ).on_duplicate_key_update(
                departure_time=departure,
                difference=str(difference),
                difference_hours=difference_hours,
                push_time=push_time,
                source="test_seed_script",
                updated_at=datetime.utcnow(),
            )
            db.session.execute(stmt)
            stay_count += 1

        generated_days += 1
        day_cursor += timedelta(days=1)

    db.session.commit()

    return {
        "start_date": january_start.isoformat(),
        "end_date": (feb_start - timedelta(days=1)).isoformat(),
        "days": generated_days,
        "stay_rows": stay_count,
        "append_mode": append,
        "year": year,
    }


def main():
    args = parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    max_per_day = min(args.max_per_day, 100)
    if max_per_day < 1:
        raise ValueError("--max-per-day must be at least 1.")
    if args.min_per_day < 1:
        raise ValueError("--min-per-day must be at least 1.")
    if args.min_per_day > max_per_day:
        raise ValueError("--min-per-day cannot be greater than --max-per-day.")

    app = create_app()
    with app.app_context():
        summary = seed_january_stay_times(
            year=args.year,
            min_per_day=args.min_per_day,
            max_per_day=max_per_day,
            append=args.append,
        )

    print("Seed complete")
    print(f"Year: {summary['year']}")
    print(f"Range: {summary['start_date']} to {summary['end_date']}")
    print(f"Days generated: {summary['days']}")
    print(f"patient_stay_times: {summary['stay_rows']}")
    print(f"Append mode: {summary['append_mode']}")


if __name__ == "__main__":
    main()
