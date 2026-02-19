from extensions.extensions import db

class LastUpdateStatus(db.Model):
    __tablename__ = 'last_update_status'

    id = db.Column(db.Integer, primary_key=True)
    last_updated = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())