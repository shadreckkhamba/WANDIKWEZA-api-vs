from extensions.extensions import db
from datetime import datetime

class PatientRefundCount(db.Model):
    __tablename__ = 'patient_refund_count'

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, nullable=False, index=True)
    refund_timestamp = db.Column(db.DateTime, nullable=False, index=True)
    count = db.Column(db.Integer, nullable=False, default=1)
    total = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('patient_id', 'refund_timestamp', name='uq_patient_refund_count'),
    )
