from extensions.extensions import db, dt

class PatientStayTime(db.Model):
    __tablename__ = 'patient_stay_times'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    patient_id = db.Column(db.String(20), nullable=False, comment='Unique patient identifier')

    arrival_time = db.Column(db.DateTime, nullable=False, comment='Time of patient arrival')
    departure_time = db.Column(db.DateTime, nullable=True, comment='Time of patient departure')
    difference = db.Column(db.DateTime, nullable=True, comment='Length of stay (hh:mm:ss)')
    difference_hours = db.Column(db.Float, nullable=True, comment='Stay times in hours')

    daily_average = db.Column(db.Float, nullable=True, comment='Average stay duration for that day')
    percent_change = db.Column(db.Float, nullable=True, comment='Percent change from previous average')

    push_time = db.Column(db.DateTime, nullable=False, comment='Timestamp when data was pushed')
    source = db.Column(db.String(50), nullable=False, default='timemachine', comment='Source of the data')

    created_at = db.Column(db.DateTime, default=dt.utcnow, comment='Row creation timestamp')
    updated_at = db.Column(db.DateTime, default=dt.utcnow, onupdate=dt.utcnow, comment='Row update timestamp')

    __table_args__ = (
        db.UniqueConstraint('patient_id', 'arrival_time', name='uix_patient_stay'),
    )

    def __repr__(self):
        return (
            f"<PatientStayTime patient_id={self.patient_id}, "
            f"arrival={self.arrival_time}, departure={self.departure_time}, "
            f"difference={self.difference}, push_time={self.push_time}>"
        )