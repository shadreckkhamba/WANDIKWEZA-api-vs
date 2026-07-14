import logging
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

from utils.config import load_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

config = load_config()

db = SQLAlchemy()
dt = datetime

db_uri = config.get('database', {}).get('db_uri')
VIRTUAL_SERVER_ADDRESS = f"{config['virtual_server']['host']}:{config['virtual_server']['port']}"
