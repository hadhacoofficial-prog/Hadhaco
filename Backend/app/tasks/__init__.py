"""Celery task modules. Imported eagerly so every ``@celery_app.task``
decorator registers regardless of which module happens to import first —
``app/celery_app.py``'s ``include=["app.tasks"]`` triggers this import when
the Celery app is instantiated."""

from __future__ import annotations

from app.tasks import (  # noqa: F401
    admin,
    cms,
    inventory,
    maintenance,
    media,
    notifications,
)

__all__ = [
    "admin",
    "cms",
    "inventory",
    "maintenance",
    "media",
    "notifications",
]
