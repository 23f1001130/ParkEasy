from flask import Flask
from flask_mail import Mail
from models import db, Admin, ParkingLot, ParkingSpot
from werkzeug.security import generate_password_hash
from extensions import cache, make_celery

mail = Mail()


def create_app():
    app = Flask(__name__)

    # Database configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///parking_app.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'

    # Cache configuration (Redis)
    app.config['CACHE_TYPE'] = 'redis'
    app.config['CACHE_REDIS_URL'] = 'redis://localhost:6379/0'
    app.config['CACHE_DEFAULT_TIMEOUT'] = 300

    # Celery + Redis 
    app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
    app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'
    app.config['CELERY_ACCEPT_CONTENT'] = ['json']
    app.config['CELERY_TASK_SERIALIZER'] = 'json'
    app.config['CELERY_RESULT_SERIALIZER'] = 'json'
    app.config['CELERY_TIMEZONE'] = 'UTC'

    # Email configuration
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USE_SSL'] = False
    app.config['MAIL_USERNAME'] = ''
    app.config['MAIL_PASSWORD'] = ''
    app.config['MAIL_DEFAULT_SENDER'] = ''

    # Initialize extensions
    db.init_app(app)
    mail.init_app(app)
    cache.init_app(app)

    # Register blueprints
    from routes import main
    app.register_blueprint(main)

    return app

def seed_initial_data(app):
  
    with app.app_context():
        
        db.create_all()

       
        if not Admin.query.first():
            admin = Admin(
                username='admin', 
                password=generate_password_hash('admin123')
            )
            db.session.add(admin)
            print("✓ Default admin created (username: admin, password: admin123)")

      
        if not ParkingLot.query.first():
            lot = ParkingLot(
                lot_name='Main Campus Lot',
                address='Campus Gate, University Road',
                pincode='123456',
                price_per_hour=50.0,
                number_of_spots=10,
                is_active=True
            )
            db.session.add(lot)
            db.session.flush()  

            
            for i in range(1, lot.number_of_spots + 1):
                spot = ParkingSpot(
                    spot_number=str(i),
                    lot_id=lot.id,
                    status='A',  
                    is_active=True
                )
                db.session.add(spot)

        try:
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
           

if __name__ == '__main__':
    app = create_app()
    
    
    seed_initial_data(app)
    
    
    app.run(debug=True, host='127.0.0.1', port=5000)