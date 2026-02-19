from flask import Flask
from flask_migrate import Migrate
from flask_cors import CORS

def create_app():
    app = Flask(__name__)
    from extensions.extensions import db_uri, db

    # Database configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # usually best to disable for performance
    
    CORS(app)

    # Initialize extensions
    db.init_app(app)

    # Set up Flask-Migrate
    Migrate(app, db)

    # Import and register Blueprints with prefix
    from routes.wandikweza_route import wandikweza_bp

    # Register the Blueprint at /wandikweza
    app.register_blueprint(wandikweza_bp, url_prefix='/wandikweza')

    return app
