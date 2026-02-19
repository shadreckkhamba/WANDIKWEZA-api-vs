from flask import Blueprint, request, jsonify
from services.patient_categories_service import save_patient_data
from models.last_update_status_model import LastUpdateStatus
from extensions.extensions import db
from pytz import timezone, utc
import logging
import gzip
import json
from io import BytesIO

logger = logging.getLogger(__name__)

wandikweza_bp = Blueprint('wandikweza', __name__)

# Malawi timezone for conversion
LOCAL_TZ = timezone('Africa/Blantyre')

@wandikweza_bp.route('/save_patient_data', methods=['POST'])
@wandikweza_bp.route('/save_patient_data/', methods=['POST'])

def save_patient_category_data_route():
    try:
        if request.headers.get("Content-Encoding") == "gzip":
            # Decompress gzipped body
            compressed_data = request.get_data()
            decompressed_data = gzip.GzipFile(fileobj=BytesIO(compressed_data)).read()
            data = json.loads(decompressed_data.decode("utf-8"))
        else:
            # Normal JSON
            data = request.get_json()

        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400

        result = save_patient_data(data)
        logger.info("Successfully returned patient data")

        if "error" in result:
            logger.error("Error in save_patient_data result")
            return jsonify(result), 500

        return jsonify(result), 200

    except Exception as e:
        logger.exception("Failed to process request")
        return jsonify({"error": str(e)}), 500


@wandikweza_bp.route('/last_update_status', methods=['GET'])
def get_last_update_status():
    """
    Route: Returns the last updated timestamp
    """
    last = db.session.query(LastUpdateStatus).order_by(LastUpdateStatus.last_updated.desc()).first()
    if not last or not last.last_updated:
        return jsonify({"last_updated": None}), 200

    last_updated_utc = last.last_updated
    if last_updated_utc.tzinfo is None:
        last_updated_utc = last_updated_utc.replace(tzinfo=utc)

    last_updated_local = last_updated_utc.astimezone(LOCAL_TZ)

    return jsonify({"last_updated": last_updated_local.isoformat()}), 200
