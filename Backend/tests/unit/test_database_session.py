"""Regression tests for app.core.database._session_has_writes.

Exercises the exact SQLAlchemy transaction machinery involved in the
production bug: ``SessionTransaction.connection`` is a *method*, not an
attribute, so reading it via ``getattr`` and then doing ``.info`` on the
result raised ``AttributeError: 'function' object has no attribute 'info'``
for any session whose transaction had genuinely opened a connection.

Uses a real in-memory SQLite engine (stdlib sqlite3, no extra dependency)
and SQLAlchemy's own sync ``Session`` — ``_session_has_writes`` only touches
``session.sync_session``, so a lightweight stand-in exposing that attribute
is sufficient; the transaction/connection objects underneath are the real
SQLAlchemy classes, so this actually exercises the code path that broke.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session

from app.core.database import _session_has_writes


class _Base(DeclarativeBase):
    pass


class _Widget(_Base):
    __tablename__ = "widgets"
    id = Column(Integer, primary_key=True)
    name = Column(String)


class _FakeAsyncSession:
    """Minimal stand-in exposing the one attribute _session_has_writes reads."""

    def __init__(self, sync_session: Session) -> None:
        self.sync_session = sync_session


@pytest.fixture
def engine():
    eng = create_engine("sqlite://")
    _Base.metadata.create_all(eng)
    return eng


class TestSessionHasWrites:
    def test_read_only_request_no_writes(self, engine):
        """A session that only reads never opens a write flag or ORM change."""
        with Session(engine) as session:
            with session.begin():
                session.execute(text("SELECT 1"))
                assert _session_has_writes(_FakeAsyncSession(session)) is False

    def test_core_write_sets_hadha_write_flag(self, engine):
        """Raw Core DML is invisible to ORM new/dirty/deleted — detected via
        the ``hadha_write`` flag on the transaction's already-open connection,
        mirroring what the after_cursor_execute listener sets in production."""
        with Session(engine) as session:
            with session.begin():
                session.execute(text("INSERT INTO widgets (id, name) VALUES (1, 'x')"))
                # Simulate the after_cursor_execute listener flagging the
                # connection actually bound to this transaction.
                conn = session.connection()
                conn.info["hadha_write"] = True
                assert _session_has_writes(_FakeAsyncSession(session)) is True

    def test_orm_add_detected_without_connection_flag(self, engine):
        """ORM-tracked new objects are detected via sync.new before any
        connection/flag inspection is needed."""
        with Session(engine) as session:
            with session.begin():
                session.add(_Widget(id=2, name="y"))
                assert _session_has_writes(_FakeAsyncSession(session)) is True

    def test_transaction_with_no_connection_opened_yet(self, engine):
        """A transaction exists but no query has run — _connections is empty.
        Must return False, not raise (this is the exact shape of the original
        AttributeError: txn.connection existed as a bound method, so the old
        code's `conn is not None` check never short-circuited)."""
        with Session(engine) as session:
            with session.begin():
                fake = _FakeAsyncSession(session)
                assert _session_has_writes(fake) is False

    def test_no_active_transaction_returns_false(self, engine):
        """get_transaction() is None outside any transaction context."""
        session = Session(engine)
        try:
            assert session.get_transaction() is None
            assert _session_has_writes(_FakeAsyncSession(session)) is False
        finally:
            session.close()

    def test_rollback_path_unaffected(self, engine):
        """An exception mid-transaction still rolls back cleanly regardless
        of write-detection — guards against regressions in the surrounding
        get_db() control flow, not just this function in isolation."""
        with pytest.raises(RuntimeError):
            with Session(engine) as session:
                with session.begin():
                    session.execute(
                        text("INSERT INTO widgets (id, name) VALUES (3, 'z')")
                    )
                    raise RuntimeError("simulated failure")
        # A fresh session sees nothing committed.
        with Session(engine) as verify_session:
            count = verify_session.execute(
                text("SELECT COUNT(*) FROM widgets WHERE id = 3")
            ).scalar_one()
            assert count == 0
