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
from sqlalchemy import func

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

def upsert_patient_gender_count(gender, time_stamp, total):
    try:
        obj = db.session.query(PatientGenderCount).filter_by(
            gender=gender,
            time_stamp=time_stamp
        ).first()

        if obj:
            obj.total = total
            obj.updated_at = datetime.utcnow()
        else:
            obj = PatientGenderCount(
                patient_id=None, 
                gender=gender,
                time_stamp=time_stamp,
                total=total,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.session.add(obj)

        db.session.commit()
    except Exception as e:
        logger.exception(f"Failed to upsert gender count: {e}")
        db.session.rollback()

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
    # Try to get the singleton row
    last_update = db.session.query(LastUpdateStatus).get(1)  # get by primary key

    if not last_update:
        # If not exists, create it
        last_update = LastUpdateStatus(id=1, last_updated=current_date)
        db.session.add(last_update)
    else:
        # Update the field
        last_update.last_updated = current_date

    db.session.commit()

from sqlalchemy.dialects.mysql import insert as mysql_insert

def save_patient_data(data):
    """
    Save patient data with upserts, aggregating totals on duplicates.
    """
    current_date = datetime.utcnow()
    age_categories = data.get("age_categories", [])
    gender_counts = data.get("gender_counts", [])
    refunded_patients = data.get("refunded_patients", [])
    location_counts = data.get("location_counts", [])

    try:
        # --- Age Categories ---
        for item in age_categories:
            raw_date = item.get("time_stamp") or item.get("period_date")
            time_stamp = parse_period_date(raw_date)
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
                db.session.execute(stmt)

        # --- Gender Counts ---
        # --- Gender Counts ---
        from collections import Counter

        # Aggregate total visits per gender first
        monthly_totals = Counter()
        # --- Gender Counts ---
        for item in gender_counts:
            raw_date = item.get("time_stamp")
            time_stamp = parse_period_date(raw_date)
            patient_id = item.get("patient_id")
            gender = item.get("gender")
            total = int(item.get("total") or 1)

            if time_stamp and patient_id and gender:
                stmt = mysql_insert(PatientGenderCount).values(
                    patient_id=patient_id,
                    gender=gender,
                    time_stamp=time_stamp,
                    total=total,
                    created_at=current_date,
                    updated_at=current_date
                ).on_duplicate_key_update(
                    total=PatientGenderCount.total + total,
                    updated_at=current_date
                )

                db.session.execute(stmt)



        # --- Refunded Patients ---
        for item in refunded_patients:
            raw_date = item.get("refund_timestamp") or item.get("time_stamp") or item.get("period_date")
            refund_timestamp = parse_period_date(raw_date)
            patient_id = item.get("patient_id") or item.get("id")

            if refund_timestamp and patient_id is not None:
                stmt = mysql_insert(PatientRefundCount).values(
                    patient_id=patient_id,
                    refund_timestamp=refund_timestamp,
                    count=1,
                    total=0,
                    created_at=current_date,
                    updated_at=current_date
            )
            stmt = stmt.on_duplicate_key_update(
                # Keep the same count or increment if needed
                count=PatientRefundCount.count,  # keeps the current value
                updated_at=current_date
            )
            db.session.execute(stmt)

        # After loop, compute global total once
        total = db.session.query(func.count(PatientRefundCount.patient_id.distinct())).scalar()
        db.session.query(PatientRefundCount).update({
            PatientRefundCount.total: total,
            PatientRefundCount.updated_at: current_date
        })

        db.session.commit()

        # --- Location Counts ---
        for item in location_counts:
            raw_date = item.get("time_stamp") or item.get("period_date")
            time_stamp = parse_period_date(raw_date)
            location = item.get("location")
            patient_id = item.get("patient_id") or item.get("id")
            count = int(item.get("total") or item.get("count") or 1)

            stmt = mysql_insert(PatientLocationCount).values(
                patient_id=patient_id,
                location=location,
                time_stamp=time_stamp,
                total=count,
                created_at=current_date,
                updated_at=current_date
            )
            stmt = stmt.on_duplicate_key_update(
                total=count,               
                time_stamp=time_stamp,  
                updated_at=current_date
            )
            db.session.execute(stmt)


        # Commit all upserts at once
        db.session.commit()
        logger.info("All patient data upserted successfully")

        # Update last_updated timestamp
        update_last_updated_if_needed()

        return {"message": "Patient data saved successfully"}

    except Exception:
        logger.exception("Error saving patient data")
        db.session.rollback()
        return {"error": "Internal server error"}

# Update the last updated timestamp
def update_last_updated_if_needed():

    latest_age = db.session.query(func.max(PatientAgeCategory.created_at)).scalar()
    latest_gender = db.session.query(func.max(PatientGenderCount.created_at)).scalar()
    latest_refund = db.session.query(func.max(PatientRefundCount.created_at)).scalar()
    latest_location = db.session.query(func.max(PatientLocationCount.created_at)).scalar()

    latest_times = [t for t in [latest_age, latest_gender, latest_refund, latest_location] if t]

    if not latest_times:
        logger.info("No data in any table, skipping last update status.")
        return

    most_recent = max(latest_times)

    record = db.session.query(LastUpdateStatus).first()
    if not record:
        db.session.add(LastUpdateStatus(last_updated=most_recent))
        logger.info(f"Created new last_update_status with {most_recent}")
    elif most_recent > record.last_updated:
        record.last_updated = most_recent
        logger.info(f"Updated last_update_status to {most_recent}")
    else:
        logger.info(f"No new data detected. last_update_status remains at {record.last_updated}")

    db.session.commit()
