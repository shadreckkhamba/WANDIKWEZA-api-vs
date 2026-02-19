import mysql.connector
import logging
import yaml
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with open('config/dev_config.yaml', 'r') as config_file:
    config = yaml.safe_load(config_file)

db = SQLAlchemy()
dt = datetime

db_uri = config['database']['db_uri']
VIRTUAL_SERVER_ADDRESS = f"{config['virtual_server']['host']}:{config['virtual_server']['port']}"