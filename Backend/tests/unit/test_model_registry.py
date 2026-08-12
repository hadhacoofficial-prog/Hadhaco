"""Regression test for app.core.model_registry.import_all_models.

Production incident: app.workers.media_generation's flush of an Image row
raised

    sqlalchemy.exc.NoReferencedTableError: Foreign key associated with
    column 'images.uploaded_by' could not find table 'profiles' with which
    to generate a foreign key to target column 'id'

in the celery-worker-media process. Root cause: Celery's
``include=["app.tasks"]`` only imports what the task modules transitively
need — app.workers.media_generation imports app.modules.media.repository but
never app.modules.profiles.models, so profiles' Table object was never
attached to Base.metadata in that process, and SQLAlchemy couldn't resolve
the images.uploaded_by -> profiles.id ForeignKey when flushing.

Note: because the full test suite runs in one shared process, other test
modules may have already imported every model by the time this test runs —
so this test cannot reliably assert profiles is *absent* beforehand (that
precondition only reproduces in an actually-isolated fresh process, which is
what the real Celery worker is). What it *can* assert, regardless of prior
state, is the thing that actually broke: that the exact failing operation
(resolving Image's mapper for a flush) succeeds after import_all_models().
"""

from __future__ import annotations

from app.core.database import Base
from app.core.model_registry import import_all_models


class TestImportAllModels:
    def test_registers_profiles_table(self) -> None:
        import_all_models()
        assert "profiles" in Base.metadata.tables

    def test_registers_images_table(self) -> None:
        import_all_models()
        assert "images" in Base.metadata.tables

    def test_registers_a_substantial_number_of_tables(self) -> None:
        """Sanity check against a no-op regression (e.g. the loop silently
        matching zero modules)."""
        import_all_models()
        assert len(Base.metadata.tables) >= 40

    def test_is_idempotent(self) -> None:
        """Celery calls this at module level in app.celery_app, which every
        process type importing it (worker, beat, or the API dispatching a
        task) triggers — must be safe to run more than once per process."""
        import_all_models()
        count_after_first = len(Base.metadata.tables)
        import_all_models()
        assert len(Base.metadata.tables) == count_after_first

    def test_image_mapper_resolves_cross_module_foreign_key(self) -> None:
        """The exact operation that raised NoReferencedTableError in
        production: Image.uploaded_by has ForeignKey("profiles.id"), and
        db.flush() needs the mapper's sorted-tables (topological FK order)
        to succeed, which requires profiles' Table object to already be
        registered."""
        import_all_models()
        from app.modules.media.models import Image

        # Raises NoReferencedTableError if profiles was never imported.
        sorted_tables = Image.__mapper__._sorted_tables
        assert sorted_tables is not None


class TestCeleryAppTriggersModelRegistration:
    def test_importing_celery_app_registers_all_models(self) -> None:
        """app.celery_app calls import_all_models() at module level — this
        is what actually protects every Celery process, since task modules
        alone don't import every models.py."""
        import app.celery_app  # noqa: F401

        assert "profiles" in Base.metadata.tables
        assert "images" in Base.metadata.tables
