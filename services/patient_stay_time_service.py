from extensions.extensions import db, logger
from models.patient_stay_time_model import PatientStayTime
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy import func
from datetime import datetime, timedelta, timezone
from typing import List, Dict
import threading
import time
import requests
import yaml
from app import create_app
from email.utils import parsedate_to_datetime

# Create a single Flask app instance
app = create_app()

# Load configuration
with open('config/dev_config.yaml', 'r') as config_file:
    config = yaml.safe_load(config_file)

def parse_time_safe(value: str):
    """Parse HH:MM:SS string into Python time object."""
    if not value:
        return None
    try:
        from datetime import datetime as dt
        return dt.strptime(value, "%H:%M:%S").time()
    except Exception as e:
        logger.warning(f"Failed to parse time '{value}': {e}")
        return None

def parse_datetime_safe(value: str):
    """Parse ISO or RFC 2822 datetime string into Python datetime object."""
    if not value:
        return None
    try:
        # Try ISO first
        return datetime.fromisoformat(value)
    except Exception:
        try:
            # Fallback: parse RFC 2822 / GMT like "Mon, 02 Feb 2026 15:56:40 GMT"
            dt = parsedate_to_datetime(value)
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception as e:
            logger.warning(f"Failed to parse datetime '{value}': {e}")
            return None

def calculate_difference(arrival_time, departure_time) -> timedelta | None:
    """Compute the difference between two time objects as timedelta, handles overnight shifts."""
    if not arrival_time or not departure_time:
        return None
    today = datetime.today()
    dt_arrival = datetime.combine(today, arrival_time)
    dt_departure = datetime.combine(today, departure_time)
    if dt_departure < dt_arrival:  # crossed midnight
        dt_departure += timedelta(days=1)
    return dt_departure - dt_arrival

# Configuration from YAML
SOURCE_URL = config['api_endpoints']['stay_times']
FETCH_INTERVAL = config['api_endpoints']['fetch_interval']

def fetch_and_save_stay_times():
    """
    Background loop that fetches stay times from SOURCE_URL and saves to DB.
    Runs inside Flask app context.
    """
    while True:
        try:
            resp = requests.get(SOURCE_URL, timeout=30)
            resp.raise_for_status()

            data = resp.json()
            entries = data.get("patient_visits") or data.get("entries") or []
            logger.info(f"Fetched {len(entries)} stay_time entries from source API")

            # Execute DB operations inside app context
            with app.app_context():
                saved_count = save_stay_times(entries)
                logger.info(f"Successfully saved {saved_count} stay_time records")

        except requests.Timeout:
            logger.warning(f"Timeout fetching stay_times from {SOURCE_URL}")
        except requests.RequestException as e:
            logger.error(f"Request failed fetching stay_times: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error in stay_times fetch/save loop: {e}")

        time.sleep(FETCH_INTERVAL)

def start_stay_time_service():
    """
    Launch the fetch_and_save_stay_times loop in a daemon thread.
    Call this once from your Flask app entry point.
    """
    thread = threading.Thread(target=fetch_and_save_stay_times, daemon=True)
    thread.start()
    logger.info("Started stay_time background fetch service")

def save_stay_times(entries: List[Dict], source_default: str = "timemachine") -> int:
    """
    Simplified stay time processing: saves raw data only, no calculated fields.
    All calculations are now done dynamically in the API endpoints.
    """
    if not entries:
        logger.info("No stay_time entries to save")
        return 0

    current_date = datetime.utcnow()
    saved_count = 0

    try:
        # Parse and prepare all entries
        parsed_entries = []
        for item in entries:
            patient_id = item.get("patient_id") or item.get("edim_patient_id")
            arrival_time = parse_datetime_safe(item.get("arrival_time"))
            departure_time = parse_datetime_safe(item.get("departure_time"))  # Can be None for active patients
            push_time = parse_datetime_safe(item.get("push_time")) or current_date
            source = item.get("source", source_default)

            if not patient_id or not arrival_time:
                logger.warning(f"Skipping incomplete record (missing patient_id or arrival_time): {item}")
                continue

            # Calculate difference_hours only if departure_time exists
            difference_hours = None
            if departure_time:
                difference_hours = round((departure_time - arrival_time).total_seconds() / 3600, 2)
            
            parsed_entries.append({
                'patient_id': str(patient_id),
                'arrival_time': arrival_time,
                'departure_time': departure_time,  # Can be None
                'push_time': push_time,
                'source': source,
                'difference_hours': difference_hours
            })

        # Don't filter out existing records - let the upsert handle both inserts and updates
        # This allows departure_time to be updated when a patient departs
        
        if not parsed_entries:
            logger.info("No valid entries to process")
            return 0

        # Process all entries - save raw data only
        for entry in parsed_entries:
            # Calculate difference timedelta for the difference field (only if departure exists)
            difference = None
            if entry['departure_time']:
                difference = entry['departure_time'] - entry['arrival_time']

            # Use upsert to handle both inserts and updates
            stmt = mysql_insert(PatientStayTime).values(
                patient_id=entry['patient_id'],
                arrival_time=entry['arrival_time'],
                departure_time=entry['departure_time'],
                difference=str(difference) if difference else None,
                difference_hours=entry['difference_hours'],
                push_time=entry['push_time'],
                source=entry['source'],
                daily_average=None,  # No longer calculated here
                percent_change=None,  # No longer calculated here
                created_at=current_date,
                updated_at=current_date,
            ).on_duplicate_key_update(
                departure_time=entry['departure_time'],
                difference=str(difference) if difference else None,
                difference_hours=entry['difference_hours'],
                push_time=entry['push_time'],
                source=entry['source'],
                updated_at=current_date,
            )

            db.session.execute(stmt)
            saved_count += 1

        db.session.commit()
        logger.info(f"Processed {saved_count} stay_time records (inserts + updates).")
        return saved_count

    except Exception as e:
        logger.exception(f"Failed to save stay_time data: {e}")
        db.session.rollback()
        raise