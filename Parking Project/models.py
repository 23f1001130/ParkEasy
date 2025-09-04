from datetime import datetime
from werkzeug.security import generate_password_hash

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy() 

# Enum-like class for spot status
class SpotStatus:
    AVAILABLE = 'A'
    OCCUPIED = 'O'

# User table: for regular users 

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    
  
    fullname = db.Column(db.String(200), nullable=True)
    address = db.Column(db.Text, nullable=True)  
    pincode = db.Column(db.String(10), nullable=True)
    
    preferred_contact = db.Column(db.String(10), default='email')
    created_on = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    parking_records = db.relationship('ParkingRecord', backref='user', lazy=True)

# Admin table: only 1 admin, auto-created
class Admin(db.Model):
    __tablename__ = 'admin'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    created_on = db.Column(db.DateTime, default=datetime.utcnow)

# ParkingLot: parent table for parking areas
class ParkingLot(db.Model):
    __tablename__ = 'parking_lots'

    id = db.Column(db.Integer, primary_key=True)
    lot_name = db.Column(db.String(100), unique=True, nullable=False)
    address = db.Column(db.String(255), nullable=False)
    pincode = db.Column(db.String(10), nullable=False)
    price_per_hour = db.Column(db.Float, nullable=False)
    number_of_spots = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_on = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    spots = db.relationship('ParkingSpot', backref='lot', lazy=True)

# ParkingSpot: individual spot in a lot
class ParkingSpot(db.Model):
    __tablename__ = 'parking_spots'

    id = db.Column(db.Integer, primary_key=True)
    spot_number = db.Column(db.String(10), nullable=False)
    lot_id = db.Column(db.Integer, db.ForeignKey('parking_lots.id'), nullable=False)
    status = db.Column(db.String(1), default=SpotStatus.AVAILABLE)  # 'A' or 'O'
    is_active = db.Column(db.Boolean, default=True)
    created_on = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    parking_records = db.relationship('ParkingRecord', backref='spot', lazy=True)

# ParkingRecord: tracks parking events
class ParkingRecord(db.Model):
    __tablename__ = 'parking_records'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    spot_id = db.Column(db.Integer, db.ForeignKey('parking_spots.id'), nullable=False)
    vehicle_number = db.Column(db.String(20), nullable=True)
    parked_at = db.Column(db.DateTime, default=datetime.utcnow)
    left_at = db.Column(db.DateTime, nullable=True)
    parking_cost = db.Column(db.Float, default=0.0)
    remarks = db.Column(db.String(255), nullable=True)

# Optional: Task tracking for async jobs (like CSV or report)
class TaskStatus(db.Model):
    __tablename__ = 'task_status'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    task_type = db.Column(db.String(50))  # e.g., "csv_export", "monthly_report"
    status = db.Column(db.String(20))  # e.g., "pending", "completed", "failed"
    result_file_path = db.Column(db.String(255))
    created_on = db.Column(db.DateTime, default=datetime.utcnow)

# Reservation: for booking a parking spot
class Reservation(db.Model):
    __tablename__ = 'reservations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    spot_id = db.Column(db.Integer, db.ForeignKey('parking_spots.id'), nullable=False)
    reserved_from = db.Column(db.DateTime, nullable=False)
    reserved_until = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='active')  # active, cancelled, completed
    created_on = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='reservations')
    spot = db.relationship('ParkingSpot', backref='reservations')

