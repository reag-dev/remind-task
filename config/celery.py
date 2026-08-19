import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("remind_task")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(name="config.debug_task")
def debug_task():
    """Task trivial para validar que worker e beat estão vivos."""
    return "pong"
