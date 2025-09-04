from celery import Celery
from celery.schedules import crontab

def make_celery(app_name=__name__):
    celery = Celery(app_name)
    
    # Configure Celery
    celery.conf.update(
        broker_url='redis://localhost:6379/0',
        result_backend='redis://localhost:6379/0',
        task_serializer='json',
        result_serializer='json',
        accept_content=['json'],
        timezone='Asia/Kolkata',
        enable_utc=True,
    )
    
    # Configure Celery Beat schedule for periodic tasks
    celery.conf.beat_schedule = {
        # Free expired spots every 5 minutes
        'free-expired-spots': {
            'task': 'tasks.free_expired_spots',
            'schedule': 300.0,  # 5 minutes
        },
        # Send daily inactive user reminders at 6 PM
        'daily-inactive-reminder': {
            'task': 'tasks.send_daily_inactive_reminder',
            'schedule': crontab(hour=18, minute=0),  # 6:00 PM daily
        },
        # Send monthly reports on 1st of each month at 9 AM
        'monthly-reports': {
            'task': 'tasks.send_all_monthly_reports',
            'schedule': crontab(day_of_month=1, hour=9, minute=0),
        },
    }
    
    # Context-aware task base
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from main import create_app
            flask_app = create_app()
            with flask_app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    
    return celery

# Create the celery instance
celery = make_celery('parking_app')

# Import all tasks so they get registered
from tasks import *