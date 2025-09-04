from flask_caching import Cache
from celery import Celery

# Initialize extensions
cache = Cache()

def make_celery(app):
    
    celery = Celery(
        app.import_name,
        backend=app.config['CELERY_RESULT_BACKEND'],
        broker=app.config['CELERY_BROKER_URL'],
        include=['tasks']  # Include your tasks module
    )
    
    # Update celery config from Flask config
    celery.conf.update(app.config)
    
    # Configure Celery to work with Flask application context
    class ContextTask(celery.Task):
        
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    return celery