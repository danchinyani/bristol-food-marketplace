import os
from celery import Celery

# POINT CELERY AT THE DJANGO SETTINGS MODULE
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('core')

# READ CELERY CONFIG FROM DJANGO SETTINGS USING THE CELERY_ NAMESPACE
app.config_from_object('django.conf:settings', namespace='CELERY')

# AUTO-DISCOVER tasks.py IN EACH INSTALLED APP
app.autodiscover_tasks()
