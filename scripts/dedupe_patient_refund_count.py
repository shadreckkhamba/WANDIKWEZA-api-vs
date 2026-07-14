#!/usr/bin/env python3
"""
Deduplicate `patient_refund_count` and (optionally) add a UNIQUE index.

Why:
- The ingestion path uses MySQL "ON DUPLICATE KEY UPDATE".
- Without a UNIQUE constraint on (patient_id, refund_timestamp), every sync
  inserts a new row, creating duplicates.

This script:
1) Merges duplicates by summing `count` and `total` into the lowest `id`
2) Deletes the extra rows
3) Ensures a UNIQUE index exists: `uq_patient_refund_count`
"""

from __future__ import annotations

from app import create_app
from extensions.extensions import db, logger
from sqlalchemy import text


UNIQUE_INDEX_NAME = "uq_patient_refund_count"


def _scalar(sql: str, **params) -> int:
    value = db.session.execute(text(sql), params).scalar()
    return int(value or 0)


def _duplicate_stats() -> tuple[int, int]:
    dup_groups = _scalar(
        """
        SELECT COUNT(*) AS groups_count
        FROM (
          SELECT patient_id, refund_timestamp, COUNT(*) AS cnt
          FROM patient_refund_count
          GROUP BY patient_id, refund_timestamp
          HAVING cnt > 1
        ) t
        """
    )
    dup_rows = _scalar(
        """
        SELECT COALESCE(SUM(cnt) - COUNT(*), 0) AS duplicate_rows
        FROM (
          SELECT COUNT(*) AS cnt
          FROM patient_refund_count
          GROUP BY patient_id, refund_timestamp
          HAVING cnt > 1
        ) t
        """
    )
    return dup_groups, dup_rows


def _ensure_unique_index() -> None:
    existing = _scalar(
        """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'patient_refund_count'
          AND INDEX_NAME = :index_name
        """,
        index_name=UNIQUE_INDEX_NAME,
    )
    if existing:
        logger.info("Unique index already exists: %s", UNIQUE_INDEX_NAME)
        return

    logger.info("Creating unique index: %s", UNIQUE_INDEX_NAME)
    db.session.execute(
        text(
            f"""
            CREATE UNIQUE INDEX {UNIQUE_INDEX_NAME}
            ON patient_refund_count (patient_id, refund_timestamp)
            """
        )
    )


def dedupe_patient_refund_count() -> None:
    app = create_app()

    with app.app_context():
        before_groups, before_dups = _duplicate_stats()
        logger.info(
            "patient_refund_count duplicates before: %s groups, %s extra rows",
            before_groups,
            before_dups,
        )

        if before_groups:
            # Merge into the lowest id per (patient_id, refund_timestamp)
            logger.info("Merging duplicate groups (summing count/total into MIN(id))")
            db.session.execute(
                text(
                    """
                    UPDATE patient_refund_count prc
                    JOIN (
                      SELECT patient_id,
                             refund_timestamp,
                             MIN(id) AS keep_id,
                             SUM(`count`) AS sum_count,
                             SUM(total) AS sum_total
                      FROM patient_refund_count
                      GROUP BY patient_id, refund_timestamp
                      HAVING COUNT(*) > 1
                    ) d ON prc.id = d.keep_id
                    SET prc.`count` = d.sum_count,
                        prc.total = d.sum_total,
                        prc.updated_at = UTC_TIMESTAMP()
                    """
                )
            )

            # Delete extra rows
            logger.info("Deleting duplicate rows (keeping MIN(id) per group)")
            db.session.execute(
                text(
                    """
                    DELETE prc
                    FROM patient_refund_count prc
                    JOIN (
                      SELECT patient_id,
                             refund_timestamp,
                             MIN(id) AS keep_id
                      FROM patient_refund_count
                      GROUP BY patient_id, refund_timestamp
                      HAVING COUNT(*) > 1
                    ) d
                      ON prc.patient_id = d.patient_id
                     AND prc.refund_timestamp = d.refund_timestamp
                     AND prc.id <> d.keep_id
                    """
                )
            )

        _ensure_unique_index()

        db.session.commit()

        after_groups, after_dups = _duplicate_stats()
        logger.info(
            "patient_refund_count duplicates after: %s groups, %s extra rows",
            after_groups,
            after_dups,
        )


if __name__ == "__main__":
    dedupe_patient_refund_count()

