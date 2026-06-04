from flask import Blueprint, request, jsonify
import gzip
import io
import math
from services.patient_categories_service import save_patient_data_upsert
from models.last_update_status_model import LastUpdateStatus
from extensions.extensions import db
from pytz import timezone, utc
import json
from extensions.extensions import db, logger
from sqlalchemy import text
from sqlalchemy import text, func
from flask import jsonify
from datetime import datetime, timedelta
from models.patient_stay_time_model import PatientStayTime
from models.patient_age_category_model import PatientAgeCategory
from models.patient_gender_count_model import PatientGenderCount
from models.patient_location_count_model import PatientLocationCount
from models.patient_refund_count_model import PatientRefundCount

DAYS_TO_FETCH = 7
RECENT_RECORDS_COUNT = 10
STAY_DISTRIBUTION_MAX_HOURS = 10.0
STAY_DISTRIBUTION_BUCKET_MINUTES = 1


wandikweza_bp = Blueprint('wandikweza', __name__)
LOCAL_TZ = timezone('Africa/Blantyre')

from datetime import datetime, time

def parse_time_safe(value: str) -> time | None:
    """Parse HH:MM:SS string into Python time object."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M:%S").time()
    except Exception as e:
        logger.warning(f"Failed to parse time '{value}': {e}")
        return None


def parse_datetime_safe(value: str) -> datetime | None:
    """Parse full ISO datetime string into Python datetime object."""
    if not value:
        return None
    try:
        # Parse ISO 8601 string
        dt = datetime.fromisoformat(value)
        # Convert to local timezone if it has tzinfo
        if dt.tzinfo:
            dt = dt.astimezone(LOCAL_TZ)
        else:
            dt = LOCAL_TZ.localize(dt)
        return dt
    except Exception as e:
        logger.warning(f"Failed to parse datetime '{value}': {e}")
        return None

@wandikweza_bp.route('/save_patient_data', methods=['POST'])
@wandikweza_bp.route('/save_patient_data/', methods=['POST'])
def save_patient_category_data_route():
    """
    Route: Receives JSON (supports gzip), passes to service, returns response.
    """
    try:
        if request.headers.get('Content-Encoding') == 'gzip':
            compressed_data = request.get_data()
            with gzip.GzipFile(fileobj=io.BytesIO(compressed_data)) as f:
                data = f.read()
            data = json.loads(data)
        else:
            data = request.get_json()
    except Exception as e:
        return jsonify({"error": f"Failed to parse JSON payload: {str(e)}"}), 400

    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    result = save_patient_data_upsert(data)

    if "error" in result:
        return jsonify(result), 500

    return jsonify(result), 200


@wandikweza_bp.route('/last_update_status', methods=['GET'])
def get_last_update_status():
    """
    Route: Returns the last updated timestamp, converted to Malawi local time.
    """
    last = db.session.query(LastUpdateStatus).order_by(LastUpdateStatus.last_updated.desc()).first()
    if not last or not last.last_updated:
        return jsonify({"last_updated": None}), 200

    last_updated_utc = last.last_updated
    if last_updated_utc.tzinfo is None:
        last_updated_utc = last_updated_utc.replace(tzinfo=utc)

    last_updated_local = last_updated_utc.astimezone(LOCAL_TZ)

    return jsonify({"last_updated": last_updated_local.isoformat()}), 200

from models.patient_stay_time_model import PatientStayTime


from flask import jsonify
from sqlalchemy import text
from datetime import datetime, timedelta
from extensions.extensions import db, logger
from models.patient_stay_time_model import PatientStayTime

@wandikweza_bp.route('/daily_average_stay', methods=['GET'])
def get_daily_average_stay():
    """
    Returns daily average stay times calculated dynamically from raw data.
    No longer stores calculated values in DB - calculates everything on-demand.
    """
    try:
        today_dt = datetime.now()
        start_of_week = today_dt - timedelta(days=today_dt.weekday())  # Monday

        # Get all records and calculate in Python to avoid SQLAlchemy issues
        all_records = db.session.query(PatientStayTime).all()
        
        if not all_records:
            return jsonify({
                "today": {
                    "date": today_dt.strftime("%Y-%m-%d"),
                    "avg_stay_hours": 0.0,
                    "recent_avg": 0.0,
                    "percent_change": 0.0,
                    "patient_count": 0
                },
                "trend": [],
                "stay_distribution": {}
            }), 200

        # Group records by date and sort by departure time
        daily_data = {}
        for record in all_records:
            # Skip records without departure time (active patients)
            if record.difference_hours is None or record.departure_time is None:
                continue
                
            date_str = record.push_time.date().strftime("%Y-%m-%d")
            if date_str not in daily_data:
                daily_data[date_str] = []
            daily_data[date_str].append({
                'hours': float(record.difference_hours),
                'departure_time': record.departure_time
            })

        # Sort records within each day by departure time
        for date_str in daily_data:
            daily_data[date_str].sort(key=lambda x: x['departure_time'])

        # Calculate daily averages and running averages
        daily_averages = {}
        for date_str, records in daily_data.items():
            hours_list = [r['hours'] for r in records]
            daily_averages[date_str] = {
                'avg_hours': sum(hours_list) / len(hours_list),
                'count': len(hours_list),
                'records': records
            }

        # Use actual today's date
        today_str = today_dt.strftime("%Y-%m-%d")
        sorted_dates = sorted(daily_averages.keys(), reverse=True)
        
        if not sorted_dates:
            return jsonify({
                "today": {
                    "date": today_str,
                    "avg_stay_hours": 0.0,
                    "recent_avg": 0.0,
                    "percent_change": 0.0,
                    "patient_count": 0
                },
                "trend": [],
                "stay_distribution": {}
            }), 200

        # Check if today has data, otherwise use 0
        if today_str in daily_averages:
            today_records = daily_averages[today_str]['records']
            today_avg = daily_averages[today_str]['avg_hours']
            today_count = daily_averages[today_str]['count']
        else:
            today_records = []
            today_avg = 0.0
            today_count = 0

        # recent_avg is the average of today's records excluding the most recent one
        recent_avg = 0.0
        if len(today_records) > 1:
            recent_hours = [r['hours'] for r in today_records[:-1]]
            if recent_hours:
                recent_avg = sum(recent_hours) / len(recent_hours)

        # Calculate percent change
        percent_change = 0.0
        if recent_avg > 0:
            percent_change = ((today_avg - recent_avg) / recent_avg) * 100
        elif recent_avg == 0 and today_avg > 0:
            # Coming from 0 to positive value - show as 100% increase
            percent_change = 100.0
        elif recent_avg == 0 and today_avg == 0:
            # Both are 0 - no change
            percent_change = 0.0

        # Build weekly trend
        trend = []
        for i in range((today_dt - start_of_week).days + 1):
            day_dt = start_of_week + timedelta(days=i)
            day_str = day_dt.strftime("%Y-%m-%d")
            
            if day_str in daily_averages:
                avg_hours = round(daily_averages[day_str]['avg_hours'], 2)
            else:
                avg_hours = 0.0

            # Percent change vs most recent day
            day_percent_change = 0.0
            if today_avg > 0:
                day_percent_change = round(((avg_hours - today_avg) / today_avg) * 100, 2)
            elif avg_hours == 0:
                day_percent_change = 0.0
            else:
                day_percent_change = -100.0

            trend.append({
                "day": day_str,
                "avg_hours": avg_hours,
                "percent_change_vs_today": day_percent_change
            })

        # Build stay distribution buckets (10-minute buckets up to 10 hours)
        bucket_size_hours = STAY_DISTRIBUTION_BUCKET_MINUTES / 60.0
        bucket_count = int(STAY_DISTRIBUTION_MAX_HOURS / bucket_size_hours)
        bucket_counts = [0] * bucket_count

        for record in all_records:
            if record.difference_hours is None or record.departure_time is None:
                continue  # Skip active patients
            try:
                hours = float(record.difference_hours)
            except (TypeError, ValueError):
                continue
            if hours < 0 or hours >= STAY_DISTRIBUTION_MAX_HOURS:
                continue
            bucket_index = int(hours / bucket_size_hours)
            if 0 <= bucket_index < bucket_count:
                bucket_counts[bucket_index] += 1

        # Build stay distribution per day
        stay_distribution = {}
        for record in all_records:
            if record.difference_hours is None or record.push_time is None or record.departure_time is None:
                continue  # Skip active patients
            try:
                hours = float(record.difference_hours)
            except (TypeError, ValueError):
                continue
            if hours < 0 or hours >= STAY_DISTRIBUTION_MAX_HOURS:
                continue

            date_key = record.push_time.date().strftime("%Y-%m-%d")
            if date_key not in stay_distribution:
                stay_distribution[date_key] = [0] * bucket_count

            bucket_index = int(hours / bucket_size_hours)
            if 0 <= bucket_index < bucket_count:
                stay_distribution[date_key][bucket_index] += 1

        for date_key, counts in stay_distribution.items():
            stay_distribution[date_key] = [
                {"hours": round(i * bucket_size_hours, 2), "count": counts[i]}
                for i in range(bucket_count)
            ]

        response = {
            "today": {
                "date": today_str,
                "avg_stay_hours": round(today_avg, 2),
                "recent_avg": round(recent_avg, 2),
                "percent_change": round(percent_change, 2),
                "patient_count": today_count
            },
            "trend": trend,
            "stay_distribution": stay_distribution
        }

        logger.info(f"Daily average calculated: today={today_str} avg={today_avg:.2f}h ({today_count} patients), previous={recent_avg:.2f}h, change={percent_change:.2f}%")
        return jsonify(response), 200

    except Exception as e:
        logger.exception("Error in /daily_average_stay")
        return jsonify({"error": str(e)}), 500


@wandikweza_bp.route('/stay_times_distribution', methods=['GET'])
def stay_times_distribution():
    """
    Returns a list of stay time entries formatted as HH:MM:SS plus
    shortest and longest stay in decimal hours.

    Supports:
    - period=day|week|month (defaults to day)
    - date=YYYY-MM-DD for a single-day snapshot
    - start_date=YYYY-MM-DD and end_date=YYYY-MM-DD for an inclusive range
    """
    try:
        period = (request.args.get('period') or 'day').lower()
        date_str = request.args.get('date')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        now = datetime.now()
        start = None
        end_exclusive = None

        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({
                    'error': 'Invalid date format. Use YYYY-MM-DD for date.'
                }), 400
            start = datetime.combine(target_date, datetime.min.time())
            end_exclusive = start + timedelta(days=1)
        elif start_date_str or end_date_str:
            if not start_date_str or not end_date_str:
                return jsonify({
                    'error': 'Both start_date and end_date are required when filtering by range.'
                }), 400
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({
                    'error': 'Invalid date format. Use YYYY-MM-DD for start_date and end_date.'
                }), 400
            if end_date < start_date:
                return jsonify({
                    'error': 'end_date must be greater than or equal to start_date.'
                }), 400
            start = datetime.combine(start_date, datetime.min.time())
            end_exclusive = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        elif period == 'day':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_exclusive = start + timedelta(days=1)
        elif period == 'week':
            start = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end_exclusive = start + timedelta(days=7)
        elif period == 'month':
            start = (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
            if now.month == 12:
                end_exclusive = datetime(now.year + 1, 1, 1)
            else:
                end_exclusive = datetime(now.year, now.month + 1, 1)
        else:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_exclusive = start + timedelta(days=1)

        query = db.session.query(PatientStayTime).filter(PatientStayTime.arrival_time >= start)
        if end_exclusive is not None:
            query = query.filter(PatientStayTime.arrival_time < end_exclusive)

        records = query.all()

        entries = []
        shortest = None
        longest = None

        for r in records:
            hours = None
            if r.difference_hours is not None:
                try:
                    hours = float(r.difference_hours)
                except Exception:
                    hours = None

            if hours is None:
                continue

            # Convert decimal hours -> HH:MM:SS
            h = int(hours)
            m = int((hours - h) * 60)
            s = int(round((((hours - h) * 60) - m) * 60))
            # Normalize rounding overflow
            if s >= 60:
                s -= 60
                m += 1
            if m >= 60:
                m -= 60
                h += 1

            diff_str = f"{h:02d}:{m:02d}:{s:02d}"
            entries.append({"difference": diff_str})

            if shortest is None or hours < shortest:
                shortest = hours
            if longest is None or hours > longest:
                longest = hours

        response = {
            "entries": entries,
            "shortest_stay": round(shortest, 2) if shortest is not None else None,
            "longest_stay": round(longest, 2) if longest is not None else None,
        }

        filter_desc = date_str or (f"{start_date_str}..{end_date_str}" if start_date_str or end_date_str else period)
        logger.info(f"/stay_times_distribution: filter={filter_desc} entries={len(entries)} shortest={response['shortest_stay']} longest={response['longest_stay']}")
        return jsonify(response), 200

    except Exception as e:
        logger.exception("Error in /stay_times_distribution")
        return jsonify({"error": str(e)}), 500


@wandikweza_bp.route('/stay_times_trend', methods=['GET'])
def stay_times_trend():
    """
    Returns daily aggregated stay time trend data.
    Optional query params:
    - start_date=YYYY-MM-DD
    - end_date=YYYY-MM-DD
    If omitted, defaults to the last 7 days.
    Each entry contains: day (YYYY-MM-DD), avg_stay_hours, total_patients
    """
    try:
        start_date_str = request.args.get("start_date")
        end_date_str = request.args.get("end_date")

        if start_date_str or end_date_str:
            if not start_date_str or not end_date_str:
                return jsonify({
                    "error": "Both start_date and end_date are required when filtering by week."
                }), 400
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            except ValueError:
                return jsonify({
                    "error": "Invalid date format. Use YYYY-MM-DD for start_date and end_date."
                }), 400

            if end_date < start_date:
                return jsonify({
                    "error": "end_date must be greater than or equal to start_date."
                }), 400

            start_dt = datetime.combine(start_date, datetime.min.time())
            end_exclusive = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        else:
            now = datetime.now()
            start_dt = now - timedelta(days=7)
            end_exclusive = now

        records = (
            db.session.query(PatientStayTime)
            .filter(PatientStayTime.arrival_time >= start_dt)
            .filter(PatientStayTime.arrival_time < end_exclusive)
            .all()
        )

        # Group by date
        daily_data = {}
        for r in records:
            if r.arrival_time is None or r.difference_hours is None:
                continue

            try:
                if isinstance(r.arrival_time, datetime):
                    day_value = r.arrival_time.date()
                else:
                    day_value = datetime.fromisoformat(str(r.arrival_time)).date()
                date_str = day_value.strftime("%Y-%m-%d")
            except Exception:
                # Skip malformed timestamps instead of failing the entire request
                continue

            if date_str not in daily_data:
                daily_data[date_str] = {'hours': [], 'count': 0}

            try:
                hours = float(r.difference_hours)
                if not math.isfinite(hours):
                    continue
                daily_data[date_str]['hours'].append(hours)
                daily_data[date_str]['count'] += 1
            except (TypeError, ValueError):
                continue

        # Calculate daily averages
        entries = []
        for date_str in sorted(daily_data.keys()):
            data = daily_data[date_str]
            if data['hours']:
                avg_hours = sum(data['hours']) / len(data['hours'])
                entries.append({
                    "day": date_str,
                    "avg_stay_hours": round(avg_hours, 2),
                    "total_patients": data['count']
                })

        response = {"entries": entries}
        logger.info(
            f"/stay_times_trend: returned {len(entries)} days of data "
            f"for range {start_dt.isoformat()} to {end_exclusive.isoformat()} (exclusive end)"
        )
        return jsonify(response), 200

    except Exception as e:
        logger.exception("Error in /stay_times_trend")
        return jsonify({"error": str(e)}), 500


@wandikweza_bp.route('/patient_records', methods=['GET'])
def get_patient_records():
    """
    Returns individual patient records with patient_id, arrival_time, and departure_time.
    Optional query params:
    - period: 'day' | 'week' | 'month' | 'all' (defaults to 'month')
    - limit: max number of records to return (defaults to 100)
    - offset: pagination offset (defaults to 0)
    """
    try:
        period = (request.args.get('period') or 'month').lower()
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))

        now = datetime.now()
        
        # Build query based on period
        query = db.session.query(PatientStayTime)
        
        if period == 'day':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(PatientStayTime.push_time >= start)
        elif period == 'week':
            start = now - timedelta(days=7)
            query = query.filter(PatientStayTime.push_time >= start)
        elif period == 'month':
            start = now - timedelta(days=30)
            query = query.filter(PatientStayTime.push_time >= start)
        elif period == 'all':
            # No date filter for 'all'
            pass
        else:
            # Default to month if invalid period
            start = now - timedelta(days=30)
            query = query.filter(PatientStayTime.push_time >= start)

        # Order by arrival time (most recent first)
        query = query.order_by(PatientStayTime.arrival_time.desc())

        total_count = query.count()
        records = query.limit(limit).offset(offset).all()

        patients = []
        for r in records:
            # Format patient_id as identifier (e.g., PT132100)
            # If patient_id is numeric, format it; otherwise use as-is
            try:
                numeric_id = int(r.patient_id) if r.patient_id else 0
                identifier = f"PT{numeric_id}"
            except (ValueError, TypeError):
                # Already a string identifier
                identifier = r.patient_id
            
            # Determine patient status
            is_active = r.departure_time is None
            current_stay_hours = None
            
            if is_active and r.arrival_time:
                # Calculate current stay time for active patients
                current_stay_hours = round((now - r.arrival_time).total_seconds() / 3600, 2)
            
            patients.append({
                "patient_id": identifier,
                "arrival_time": r.arrival_time.isoformat() if r.arrival_time else None,
                "departure_time": r.departure_time.isoformat() if r.departure_time else None,
                "is_active": is_active,
                "stay_hours": float(r.difference_hours) if r.difference_hours else current_stay_hours
            })

        response = {
            "patients": patients,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "period": period
        }

        logger.info(f"/patient_records: period={period} returned {len(patients)} records (total={total_count})")
        return jsonify(response), 200

    except Exception as e:
        logger.exception("Error in /patient_records")
        return jsonify({"error": str(e)}), 500


@wandikweza_bp.route('/date_ranges', methods=['GET'])
def get_date_ranges():
    """
    Returns dynamic date ranges for each table based on actual data.
    For each table, returns the first day of the month to the last day data was created.
    
    Response format:
    {
        "patient_age_categories": {
            "start_date": "2026-04-01",
            "end_date": "2026-04-08",
            "table_name": "patient_age_categories",
            "date_field": "time_stamp"
        },
        ...
    }
    """
    try:
        ranges = {}
        
        # Define table configurations with their models and date fields
        table_configs = [
            {
                'key': 'patient_age_categories',
                'model': PatientAgeCategory,
                'date_field': 'time_stamp',
                'table_name': 'patient_age_categories'
            },
            {
                'key': 'patient_gender_counts', 
                'model': PatientGenderCount,
                'date_field': 'time_stamp',
                'table_name': 'patient_gender_counts'
            },
            {
                'key': 'patient_location_counts',
                'model': PatientLocationCount, 
                'date_field': 'time_stamp',
                'table_name': 'patient_location_counts'
            },
            {
                'key': 'patient_refund_count',
                'model': PatientRefundCount,
                'date_field': 'refund_timestamp', 
                'table_name': 'patient_refund_count'
            },
            {
                'key': 'patient_stay_times',
                'model': PatientStayTime,
                'date_field': 'arrival_time',
                'table_name': 'patient_stay_times'
            }
        ]
        
        for config in table_configs:
            try:
                model = config['model']
                date_field = getattr(model, config['date_field'])
                
                # Get the latest date from the table
                latest_record = db.session.query(func.max(date_field)).scalar()
                
                if latest_record:
                    # Convert to date if it's a datetime
                    if hasattr(latest_record, 'date'):
                        end_date = latest_record.date()
                    else:
                        end_date = latest_record
                    
                    # Start date is first day of the month
                    start_date = end_date.replace(day=1)
                    
                    ranges[config['key']] = {
                        'start_date': start_date.strftime('%Y-%m-%d'),
                        'end_date': end_date.strftime('%Y-%m-%d'),
                        'table_name': config['table_name'],
                        'date_field': config['date_field']
                    }
                else:
                    # No data in table
                    ranges[config['key']] = {
                        'start_date': None,
                        'end_date': None,
                        'table_name': config['table_name'],
                        'date_field': config['date_field']
                    }
                    
            except Exception as e:
                logger.warning(f"Error getting date range for {config['key']}: {str(e)}")
                ranges[config['key']] = {
                    'start_date': None,
                    'end_date': None,
                    'table_name': config['table_name'],
                    'date_field': config['date_field'],
                    'error': str(e)
                }
        
        logger.info(f"/date_ranges: returned ranges for {len(ranges)} tables")
        return jsonify(ranges), 200
        
    except Exception as e:
        logger.exception("Error in /date_ranges")
        return jsonify({"error": str(e)}), 500

@wandikweza_bp.route('/patient_stay_details/<date>', methods=['GET'])
def get_patient_stay_details(date):
    """
    Returns individual patient stay details for a specific date.
    Used to show a timeline of all patients and their stay durations.
    """
    try:
        from datetime import datetime
        
        # Validate date format
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        # Get all patient records for the specified date
        records = db.session.query(PatientStayTime).filter(
            db.func.date(PatientStayTime.arrival_time) == date
        ).order_by(PatientStayTime.departure_time).all()
        
        if not records:
            return jsonify({
                "date": date,
                "patient_count": 0,
                "patients": []
            }), 200
        
        # Format patient details
        patients = []
        for record in records:
            # Format patient_id as identifier (e.g., PT132100)
            try:
                numeric_id = int(record.patient_id) if record.patient_id else 0
                identifier = f"PT{numeric_id}"
            except (ValueError, TypeError):
                identifier = record.patient_id
            
            # Handle active patients (no departure time yet)
            is_active = record.departure_time is None
            
            if is_active:
                # Calculate current stay time for active patients
                current_stay = datetime.now() - record.arrival_time
                stay_hours = current_stay.total_seconds() / 3600
                patients.append({
                    "patient_id": identifier,
                    "arrival_time": record.arrival_time.strftime('%H:%M:%S'),
                    "departure_time": None,
                    "stay_hours": round(stay_hours, 2),
                    "stay_formatted": f"{int(stay_hours)}h {int((stay_hours % 1) * 60)}m",
                    "is_active": True
                })
            else:
                # Completed visit
                patients.append({
                    "patient_id": identifier,
                    "arrival_time": record.arrival_time.strftime('%H:%M:%S'),
                    "departure_time": record.departure_time.strftime('%H:%M:%S'),
                    "stay_hours": float(record.difference_hours) if record.difference_hours else 0.0,
                    "stay_formatted": f"{int(record.difference_hours)}h {int((record.difference_hours % 1) * 60)}m" if record.difference_hours else "0h 0m",
                    "is_active": False
                })
        
        return jsonify({
            "date": date,
            "patient_count": len(patients),
            "patients": patients,
            "average_stay": round(sum(p['stay_hours'] for p in patients) / len(patients), 2)
        }), 200
        
    except Exception as e:
        logger.exception(f"Error in /patient_stay_details/{date}")
        return jsonify({"error": str(e)}), 500

@wandikweza_bp.route('/daily_patient_details', methods=['GET'])
def get_daily_patient_details():
    """
    Returns detailed patient stay information for a specific date.
    Query param: date (YYYY-MM-DD format)
    """
    try:
        from flask import request
        date_str = request.args.get('date')
        
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        
        # Query patient details for the specified date
        query = text("""
            SELECT 
                patient_id,
                TIME(arrival_time) as arrival_time,
                TIME(departure_time) as departure_time,
                difference_hours,
                arrival_time as full_arrival,
                departure_time as full_departure
            FROM patient_stay_times
            WHERE DATE(arrival_time) = :date
            ORDER BY departure_time
        """)
        
        result = db.session.execute(query, {'date': date_str})
        patients = []
        
        for row in result:
            # Format patient_id as identifier (e.g., PT132100)
            try:
                numeric_id = int(row[0]) if row[0] else 0
                identifier = f"PT{numeric_id}"
            except (ValueError, TypeError):
                identifier = row[0]
            
            # Handle active patients (no departure time)
            is_active = row[2] is None  # departure_time
            stay_hours = float(row[3]) if row[3] is not None else None
            
            patients.append({
                'patient_id': identifier,
                'arrival_time': str(row[1]) if row[1] else None,
                'departure_time': str(row[2]) if row[2] else None,
                'stay_hours': stay_hours,
                'full_arrival': row[4].isoformat() if row[4] else None,
                'full_departure': row[5].isoformat() if row[5] else None,
                'is_active': is_active
            })
        
        logger.info(f"Patient details for {date_str}: {len(patients)} patients")
        
        return jsonify({
            'date': date_str,
            'patient_count': len(patients),
            'patients': patients
        }), 200
        
    except Exception as e:
        logger.exception("Error in /daily_patient_details")
        return jsonify({"error": str(e)}), 500


@wandikweza_bp.route('/active_patients', methods=['GET'])
def get_active_patients():
    """
    Returns patients currently in the facility (have arrival_time but no departure_time).
    Shows real-time status of patients being processed.
    """
    try:
        # Get all patients without departure times
        active_records = db.session.query(PatientStayTime).filter(
            PatientStayTime.departure_time.is_(None)
        ).order_by(PatientStayTime.arrival_time.desc()).all()
        
        now = datetime.now()
        active_patients = []
        
        for record in active_records:
            # Format patient_id as identifier
            try:
                numeric_id = int(record.patient_id) if record.patient_id else 0
                identifier = f"PT{numeric_id}"
            except (ValueError, TypeError):
                identifier = record.patient_id
            
            # Calculate current stay time
            if record.arrival_time:
                current_stay = now - record.arrival_time
                stay_hours = round(current_stay.total_seconds() / 3600, 2)
                stay_minutes = round(current_stay.total_seconds() / 60, 0)
            else:
                stay_hours = 0
                stay_minutes = 0
            
            active_patients.append({
                "patient_id": identifier,
                "arrival_time": record.arrival_time.isoformat() if record.arrival_time else None,
                "current_stay_hours": stay_hours,
                "current_stay_minutes": int(stay_minutes),
                "stay_formatted": f"{int(stay_hours)}h {int((stay_hours % 1) * 60)}m",
                "arrival_date": record.arrival_time.strftime('%Y-%m-%d') if record.arrival_time else None
            })
        
        logger.info(f"/active_patients: returned {len(active_patients)} active patients")
        
        return jsonify({
            "active_patient_count": len(active_patients),
            "patients": active_patients,
            "timestamp": now.isoformat()
        }), 200
        
    except Exception as e:
        logger.exception("Error in /active_patients")
        return jsonify({"error": str(e)}), 500
