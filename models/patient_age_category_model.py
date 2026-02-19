from extensions.extensions import db, dt

class PatientAgeCategory(db.Model):
    __tablename__ = 'patient_age_categories'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    patient_id = db.Column(db.Integer, nullable=False, comment='Unique ID of the patient')
    category = db.Column(db.String(50), nullable=False, index=True, comment='Age group label (e.g. "Under 5", "Adolescents")')
    time_stamp = db.Column(db.DateTime, nullable=False, comment='Date the data was recorded')

    created_at = db.Column(db.DateTime, default=dt.utcnow)
    updated_at = db.Column(db.DateTime, default=dt.utcnow, onupdate=dt.utcnow)

    total = db.Column(db.Integer, nullable=False, default=1, comment='Usually 1, represents a count placeholder per patient')

    def __repr__(self):
        return f"<PatientAgeCategory patient_id={self.patient_id}, category={self.category}, time_stamp={self.time_stamp}>"