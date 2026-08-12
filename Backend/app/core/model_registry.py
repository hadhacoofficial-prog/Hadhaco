"""Ensures every app/modules/*/models.py is imported, so every table is
attached to Base.metadata (and the shared mapper registry) before any ORM
operation that needs cross-module FK resolution runs.

FastAPI's app.main._mount_routers() gets this for free: importing every
router cascades into every service, which cascades into every models.py.
Celery worker/beat processes only import whatever app.tasks.* actually needs
transitively — a much narrower set — so a task that flushes a model with a
ForeignKey into another module's table can fail with
``NoReferencedTableError: ... could not find table 'X'`` if that other
module's models.py was never imported in this process. Confirmed in
production: app.workers.media_generation flushing Image (whose
``uploaded_by`` column has ``ForeignKey("profiles.id")``) never imports
app.modules.profiles.models, so profiles' Table object didn't exist yet.

This was previously solved once, locally, for Alembic (alembic/env.py's
autogenerate needs the full schema) — this generalizes that same helper so
Celery gets the same guarantee instead of duplicating the loop.
"""

from __future__ import annotations

import importlib
import pkgutil


def import_all_models() -> None:
    """Import every app.modules.<name>.models module. Idempotent — Python
    caches imports, so calling this more than once (e.g. once from
    app.celery_app and once from app.main, which already gets there via
    routers) is a cheap no-op after the first call."""
    import app.modules as modules_pkg

    for mod in pkgutil.iter_modules(modules_pkg.__path__):
        try:
            importlib.import_module(f"app.modules.{mod.name}.models")
        except ModuleNotFoundError:
            continue
