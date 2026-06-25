# LOAD CELERY APP WHEN DJANGO STARTS SO SHARED_TASK DECORATORS WORK
from .celery import app as celery_app

__all__ = ('celery_app',)
