#!/usr/bin/env python3
"""
Delete patient_stay_times records outside the valid stay range:
  - less than 5 minutes
  - more than 5 hours
"""

from app import create_app
from extensions.extensions import db, logger
from sqlalchemy import text

MIN_HOURS = 5 / 60   # 5 minutes
MAX_HOURS = 4.0      # 4 hours


def cleanup_stay_times() -> None:
    app = create_app()

    with app.app_context():
        too_short = db.session.execute(
            text("SELECT COUNT(*) FROM patient_stay_times WHERE difference_hours < :min"),
            {"min": MIN_HOURS},
        ).scalar()

        too_long = db.session.execute(
            text("SELECT COUNT(*) FROM patient_stay_times WHERE difference_hours > :max"),
            {"max": MAX_HOURS},
        ).scalar()

        logger.info("Records < 5 min: %s | Records > 5 hours: %s", too_short, too_long)

        if not too_short and not too_long:
            logger.info("Nothing to delete.")
            return

        db.session.execute(
            text(
                "DELETE FROM patient_stay_times WHERE difference_hours < :min OR difference_hours > :max"
            ),
            {"min": MIN_HOURS, "max": MAX_HOURS},
        )
        db.session.commit()

        logger.info("Deleted %s records total.", (too_short or 0) + (too_long or 0))


if __name__ == "__main__":
    cleanup_stay_times()
