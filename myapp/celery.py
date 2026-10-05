from celery import Celery

celery_app = Celery(
    "url_shortener",
    broker="redis://localhost:6379/0",
    result_backend=None,
)

celery_app.conf.update(
    task_ignore_result=True,
)