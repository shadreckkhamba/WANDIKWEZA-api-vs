from extensions.extensions import db, dt
from datetime import datetime
class PatientGenderCount(db.Model):
    __tablename__ = 'patient_gender_counts'

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    time_stamp = db.Column(db.Date, nullable=False)  # 🔧 Changed from DateTime to Date
    total = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('patient_id', 'gender', 'time_stamp', name='uq_gender_count'),
    )

    def __repr__(self):
        return f"<PatientGenderCount gender={self.gender}, time_stamp={self.time_stamp}, total={self.total}>"
