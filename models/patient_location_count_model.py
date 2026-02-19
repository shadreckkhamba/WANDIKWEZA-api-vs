from extensions.extensions import db, dt

class PatientLocationCount(db.Model):
    __tablename__ = 'patient_location_counts'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    patient_id = db.Column(db.Integer, nullable=False, comment='Unique ID of the patient')
    location = db.Column(db.String(100), nullable=False, index=True, comment='Village or area name')
    time_stamp = db.Column(db.DateTime, nullable=False, comment='Date the data was recorded')

    count = db.Column(db.Integer, nullable=False, default=1, comment='Count placeholder, typically 1 per patient')
    total = db.Column(db.Integer, nullable=False, comment='Total number of patients in the time range')

    created_at = db.Column(db.DateTime, default=dt.utcnow)
    updated_at = db.Column(db.DateTime, default=dt.utcnow, onupdate=dt.utcnow)

    def __repr__(self):
        return f"<PatientLocationCount patient_id={self.patient_id}, location={self.location}, time_stamp={self.time_stamp}>"