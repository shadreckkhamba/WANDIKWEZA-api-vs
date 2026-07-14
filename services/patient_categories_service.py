from extensions.extensions import db, logger
from models.last_update_status_model import LastUpdateStatus
from models.patient_age_category_model import PatientAgeCategory
from datetime import datetime
from dateutil import parser as date_parser
from models.patient_gender_count_model import PatientGenderCount
from models.patient_refund_count_model import PatientRefundCount
from sqlalchemy.exc import IntegrityError
from models.patient_location_count_model import PatientLocationCount
from sqlalchemy.dialects.mysql import insert

def upsert_patient_age_category(patient_id, category, time_stamp, total):
    stmt = insert(PatientAgeCategory).values(
        patient_id=patient_id,
        category=category,
        time_stamp=time_stamp,
        total=total,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    ).on_duplicate_key_update(
        total=total,
        updated_at=datetime.utcnow()
    )
    db.session.execute(stmt)
    db.session.commit()
    
# Insert or Update gender counts
def upsert_patient_gender_count(patient_id, gender, time_stamp, total):
    try:
        obj = PatientGenderCount(
            patient_id=patient_id,
            gender=gender,
            time_stamp=time_stamp,
            total=total,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.session.add(obj)
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        try:
            # Record exists, update instead
            obj = db.session.query(PatientGenderCount).filter_by(
                patient_id=patient_id,
                gender=gender,
                time_stamp=time_stamp
            ).first()
            if obj:
                obj.total = total
                obj.updated_at = datetime.utcnow()
                db.session.flush()
        except Exception as ex:
            logger.exception(f"Retry update failed: {ex}")
            db.session.rollback()
            raise
    except Exception as e:
        logger.exception(f"Failed to upsert gender count: {e}")
        db.session.rollback()
        raise

# Insert or Update refund counts
def upsert_patient_refund_count(patient_id, refund_timestamp, count, total):
    try:
        obj = db.session.query(PatientRefundCount).filter_by(
            patient_id=patient_id,
            refund_timestamp=refund_timestamp
        ).first()

        if obj:
            obj.count = count
            obj.total = total
            obj.updated_at = datetime.utcnow()
        else:
            obj = PatientRefundCount(
                patient_id=patient_id,
                refund_timestamp=refund_timestamp,
                count=count,
                total=total,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.session.add(obj)

        db.session.flush()
    except Exception as e:
        logger.exception(f"Failed to upsert patient refund count: {e}")
        db.session.rollback()
        raise


def upsert_patient_location_count(patient_id, location, time_stamp, total):
    try:
        obj = db.session.query(PatientLocationCount).filter_by(
            patient_id=patient_id,
            location=location
        ).first()

        if obj:
            # Update only if timestamp is newer, or always update total, etc.
            if time_stamp > obj.time_stamp:
                obj.time_stamp = time_stamp
            obj.total = total
            obj.updated_at = datetime.utcnow()
        else:
            obj = PatientLocationCount(
                patient_id=patient_id,
                location=location,
                time_stamp=time_stamp,
                total=total,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.session.add(obj)
        db.session.flush()
    except IntegrityError:
        #concurrent insert happened or race condition:
        db.session.rollback()
        # Retry update instead
        obj = db.session.query(PatientLocationCount).filter_by(
            patient_id=patient_id,
            location=location
        ).first()
        if obj:
            if time_stamp > obj.time_stamp:
                obj.time_stamp = time_stamp
            obj.total = total
            obj.updated_at = datetime.utcnow()
            db.session.flush()
        else:
            #This theoretically should not happen but log or raise if needed
            raise
    except Exception as e:
        logger.exception(f"Failed to upsert patient location count: {e}")
        db.session.rollback()
        raise

# Parse date string to datetime object
def parse_period_date(date_str):
    if not date_str:
        return None
    try:
        return date_parser.parse(date_str)
    except (ValueError, TypeError):
        return None
    
def update_last_update_status(current_date):
    """
    Update the singleton last-update row.
    Accepts either a naive datetime (assumed Africa/Blantyre local time)
    or a timezone-aware datetime, and stores it in UTC.
    """
    import pytz
    blantyre_tz = pytz.timezone('Africa/Blantyre')

    if current_date.tzinfo is None:
        # Naive datetime from the payload — it's local time (Africa/Blantyre)
        current_date = blantyre_tz.localize(current_date).astimezone(pytz.utc).replace(tzinfo=None)
    else:
        # Already tz-aware — just convert to UTC and strip tzinfo for storage
        current_date = current_date.astimezone(pytz.utc).replace(tzinfo=None)

    last_update = db.session.query(LastUpdateStatus).get(1)

    if not last_update:
        last_update = LastUpdateStatus(id=1, last_updated=current_date)
        db.session.add(last_update)
    else:
        last_update.last_updated = current_date

    db.session.commit()
    
from sqlalchemy.dialects.mysql import insert as mysql_insert

def save_patient_data_upsert(data):
    """
    Save patient data with upserts, aggregating totals on duplicates.
    Only updates last_update_status when at least one record is new/changed,
    using the most recent event timestamp from the payload rather than wall-clock time.
    """
    current_date = datetime.utcnow()
    age_categories = data.get("age_categories", [])
    gender_counts = data.get("gender_counts", [])
    refunded_patients = data.get("refunded_patients", [])
    location_counts = data.get("location_counts", [])

    # Track whether any row was actually inserted or updated
    rows_affected = 0

    # Collect all event timestamps from the payload to find the most recent one
    event_timestamps = []

    def _collect_ts(raw):
        ts = parse_period_date(raw)
        if ts:
            event_timestamps.append(ts)
        return ts

    try:
        # --- Age Categories ---
        for item in age_categories:
            time_stamp = _collect_ts(item.get("time_stamp") or item.get("period_date"))
            category = item.get("category") or item.get("label")
            patient_id = item.get("patient_id") or item.get("id")
            count = int(item.get("total") or item.get("count") or 1)

            if time_stamp and category is not None and patient_id is not None:
                stmt = mysql_insert(PatientAgeCategory).values(
                    patient_id=patient_id,
                    category=category,
                    time_stamp=time_stamp,
                    total=count,
                    created_at=current_date,
                    updated_at=current_date
                )
                stmt = stmt.on_duplicate_key_update(
                    total=PatientAgeCategory.total + count,
                    updated_at=current_date
                )
                result = db.session.execute(stmt)
                # rowcount is 1 for insert, 2 for update-on-duplicate, 0 for no-op
                if result.rowcount > 0:
                    rows_affected += 1

        # --- Gender Counts ---
        for item in gender_counts:
            time_stamp = _collect_ts(item.get("time_stamp") or item.get("period_date"))
            gender = item.get("gender")
            patient_id = item.get("patient_id") or item.get("id")
            count = int(item.get("total") or item.get("count") or 1)

            if time_stamp and gender is not None and patient_id is not None:
                stmt = mysql_insert(PatientGenderCount).values(
                    patient_id=patient_id,
                    gender=gender,
                    time_stamp=time_stamp,
                    total=count,
                    created_at=current_date,
                    updated_at=current_date
                )
                stmt = stmt.on_duplicate_key_update(
                    total=PatientGenderCount.total + count,
                    updated_at=current_date
                )
                result = db.session.execute(stmt)
                if result.rowcount > 0:
                    rows_affected += 1

        # --- Refunded Patients ---
        for item in refunded_patients:
            raw_date = item.get("refund_timestamp") or item.get("time_stamp") or item.get("period_date")
            refund_timestamp = _collect_ts(raw_date)
            patient_id = item.get("patient_id") or item.get("id")
            count = int(item.get("count") or 1)

            if refund_timestamp and patient_id is not None:
                stmt = mysql_insert(PatientRefundCount).values(
                    patient_id=patient_id,
                    refund_timestamp=refund_timestamp,
                    count=count,
                    total=count,
                    created_at=current_date,
                    updated_at=current_date
                )
                stmt = stmt.on_duplicate_key_update(
                    total=stmt.inserted.total,
                    count=stmt.inserted.count,
                    updated_at=current_date
                )
                result = db.session.execute(stmt)
                if result.rowcount > 0:
                    rows_affected += 1

        # --- Location Counts ---
        for item in location_counts:
            time_stamp = _collect_ts(item.get("time_stamp") or item.get("period_date"))
            location = item.get("location")
            patient_id = item.get("patient_id") or item.get("id")
            count = int(item.get("total") or item.get("count") or 1)

            if time_stamp and location is not None and patient_id is not None:
                stmt = mysql_insert(PatientLocationCount).values(
                    patient_id=patient_id,
                    location=location,
                    time_stamp=time_stamp,
                    total=count,
                    created_at=current_date,
                    updated_at=current_date
                )
                stmt = stmt.on_duplicate_key_update(
                    total=PatientLocationCount.total + count,
                    updated_at=current_date
                )
                result = db.session.execute(stmt)
                if result.rowcount > 0:
                    rows_affected += 1

        # Commit all upserts at once
        db.session.commit()
        logger.info("Patient data upserted successfully")

        # Only update last_update_status when something actually changed.
        # Use the most recent event timestamp from the payload so the dashboard
        # reflects when the data event happened, not when the API processed it.
        if rows_affected > 0:
            latest_event_ts = max(event_timestamps) if event_timestamps else current_date
            update_last_update_status(latest_event_ts)
            logger.info(f"Last update status set to most recent event timestamp: {latest_event_ts} ({rows_affected} rows affected)")
        else:
            logger.info("No new or changed records in payload — last update status unchanged")

        return {"message": "Patient data saved successfully"}

    except Exception:
        logger.exception("Error saving patient data")
        db.session.rollback()
        return {"error": "Internal server error"}
