from extensions.extensions import db, logger
from services.patient_stay_time_service import save_stay_times
from services.patient_categories_service import save_patient_data_upsert
from datetime import datetime
import threading
import time
import requests
import yaml
from app import create_app

import hashlib

# Create a single Flask app instance
app = create_app()

# Load configuration
with open('config/dev_config.yaml', 'r') as config_file:
    config = yaml.safe_load(config_file)

# Configuration from YAML
STAY_TIME_URL = config['api_endpoints']['stay_times']
PATIENT_DATA_URL = config['api_endpoints']['patient_data']
FETCH_INTERVAL = config['api_endpoints']['fetch_interval']

# Adaptive interval configuration
ADAPTIVE_ENABLED = config['api_endpoints']['adaptive_intervals']['enabled']
MIN_INTERVAL = config['api_endpoints']['adaptive_intervals']['min_interval']
MAX_INTERVAL = config['api_endpoints']['adaptive_intervals']['max_interval']
BACKOFF_MULTIPLIER = config['api_endpoints']['adaptive_intervals']['backoff_multiplier']

# Store last content hashes for fallback change detection
last_stay_time_hash = None
last_patient_data_hash = None
current_interval = FETCH_INTERVAL
no_change_count = 0

def fetch_stay_times():
    """Fetch stay times from external API with ETag/Last-Modified support"""
    try:
        headers = {}
        # Add conditional headers if we have them from previous requests
        if hasattr(fetch_stay_times, 'etag'):
            headers['If-None-Match'] = fetch_stay_times.etag
        if hasattr(fetch_stay_times, 'last_modified'):
            headers['If-Modified-Since'] = fetch_stay_times.last_modified
            
        resp = requests.get(STAY_TIME_URL, headers=headers, timeout=30)
        
        # Handle 304 Not Modified
        if resp.status_code == 304:
            logger.info("Stay times data not modified (304), skipping fetch")
            return None
            
        resp.raise_for_status()
        
        # Store ETag and Last-Modified for next request
        if 'etag' in resp.headers:
            fetch_stay_times.etag = resp.headers['etag']
        if 'last-modified' in resp.headers:
            fetch_stay_times.last_modified = resp.headers['last-modified']
            
        data = resp.json()
        entries = data.get("patient_visits") or data.get("entries") or []
        logger.info(f"Fetched {len(entries)} stay_time entries from source API")
        return entries
    except requests.Timeout:
        logger.warning(f"Timeout fetching stay_times from {STAY_TIME_URL}")
        return []
    except requests.RequestException as e:
        logger.error(f"Request failed fetching stay_times: {e}")
        return []
    except Exception as e:
        logger.exception(f"Unexpected error fetching stay_times: {e}")
        return []

def fetch_patient_data():
    """Fetch patient categories data from external API with ETag/Last-Modified support"""
    try:
        headers = {}
        # Add conditional headers if we have them from previous requests
        if hasattr(fetch_patient_data, 'etag'):
            headers['If-None-Match'] = fetch_patient_data.etag
        if hasattr(fetch_patient_data, 'last_modified'):
            headers['If-Modified-Since'] = fetch_patient_data.last_modified
            
        resp = requests.get(PATIENT_DATA_URL, headers=headers, timeout=30)
        
        # Handle 304 Not Modified
        if resp.status_code == 304:
            logger.info("Patient data not modified (304), skipping fetch")
            return None
            
        resp.raise_for_status()
        
        # Store ETag and Last-Modified for next request
        if 'etag' in resp.headers:
            fetch_patient_data.etag = resp.headers['etag']
        if 'last-modified' in resp.headers:
            fetch_patient_data.last_modified = resp.headers['last-modified']
            
        data = resp.json()
        logger.info(f"Fetched patient categories data from {PATIENT_DATA_URL}")
        return data
    except requests.Timeout:
        logger.warning(f"Timeout fetching patient data from {PATIENT_DATA_URL}")
        return None
    except requests.RequestException as e:
        logger.error(f"Request failed fetching patient data: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error fetching patient data: {e}")
        return None

def has_content_changed(data, data_type):
    """Check if content has actually changed using hash comparison"""
    global last_stay_time_hash, last_patient_data_hash
    
    if data is None:
        return False
        
    # Create hash of the data content
    content_str = str(sorted(data.items()) if isinstance(data, dict) else data)
    current_hash = hashlib.md5(content_str.encode()).hexdigest()
    
    if data_type == 'stay_time':
        if last_stay_time_hash == current_hash:
            logger.info("Stay time content unchanged (hash match), skipping processing")
            return False
        last_stay_time_hash = current_hash
        return True
    elif data_type == 'patient_data':
        if last_patient_data_hash == current_hash:
            logger.info("Patient data content unchanged (hash match), skipping processing")
            return False
        last_patient_data_hash = current_hash
        return True
    
    return True

def unified_data_fetch_loop():
    """
    Background loop that fetches all data types and saves to DB.
    Only processes data when it has actually changed.
    Uses adaptive intervals to reduce bandwidth when no changes.
    Runs inside Flask app context.
    """
    global current_interval, no_change_count
    
    while True:
        try:
            changes_detected = False
            
            with app.app_context():
                # Fetch and save stay times
                stay_time_entries = fetch_stay_times()
                if stay_time_entries is not None and has_content_changed(stay_time_entries, 'stay_time'):
                    saved_count = save_stay_times(stay_time_entries)
                    logger.info(f"Successfully saved {saved_count} NEW stay_time records")
                    changes_detected = True
                elif stay_time_entries is not None:
                    logger.debug("Stay time data fetched but no changes detected")

                # Fetch and save patient categories data
                patient_data = fetch_patient_data()
                if patient_data is not None and has_content_changed(patient_data, 'patient_data'):
                    result = save_patient_data_upsert(patient_data)
                    if "error" not in result:
                        logger.info("Successfully saved NEW patient categories data")
                        changes_detected = True
                    else:
                        logger.error(f"Failed to save patient data: {result}")
                elif patient_data is not None:
                    logger.debug("Patient data fetched but no changes detected")

            # Adaptive interval adjustment
            if ADAPTIVE_ENABLED:
                if changes_detected:
                    # Reset to minimum interval when changes are detected
                    current_interval = MIN_INTERVAL
                    no_change_count = 0
                    logger.debug(f"Changes detected, reset interval to {current_interval}s")
                else:
                    # Gradually increase interval when no changes
                    no_change_count += 1
                    if no_change_count >= 3:  # After 3 cycles with no changes
                        new_interval = min(current_interval * BACKOFF_MULTIPLIER, MAX_INTERVAL)
                        if new_interval != current_interval:
                            current_interval = new_interval
                            logger.info(f"No changes for {no_change_count} cycles, increased interval to {current_interval}s")

        except Exception as e:
            logger.exception(f"Unexpected error in unified data fetch loop: {e}")

        time.sleep(current_interval)

def start_unified_data_service():
    """
    Launch the unified data fetch loop in a daemon thread.
    Call this once from your Flask app entry point.
    """
    thread = threading.Thread(target=unified_data_fetch_loop, daemon=True)
    thread.start()
    logger.info("Started unified background data fetch service")