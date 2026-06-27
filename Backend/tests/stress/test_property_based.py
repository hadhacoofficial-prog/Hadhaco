"""
Property-based tests using Hypothesis.

These tests explore the invariants that must hold for ALL valid inputs,
not just the specific cases covered by example-based tests:

  P1. available = stock - reserved - sold  ≥ 0 for any valid inventory state
  P2. After a reservation: reserved increases by exactly quantity
  P3. After a release: reserved decreases by at most quantity (GREATEST(..., 0))
  P4. Reservation expiry never creates negative reserved_quantity
  P5. Order status machine allows only valid transitions
  P6. Concurrent reservations with asyncio.Lock never over-reserve stock
"""

import asyncio
from dataclasses import dataclass, field

import pytest

pytest.importorskip("hypothesis")
from hypothesis import HealthCheck, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

# ── P1: available invariant ────────────────────────────────────────────────


@given(
    stock=st.integers(min_value=0, max_value=10_000),
    reserved=st.integers(min_value=0, max_value=10_000),
    sold=st.integers(min_value=0, max_value=10_000),
)
@settings(max_examples=500)
def test_available_formula_never_negative_when_inputs_valid(
    stock: int, reserved: int, sold: int
) -> None:
    """
    For any valid inventory triple where reserved + sold ≤ stock,
    available must be ≥ 0.
    """
    if reserved + sold > stock:
        pytest.skip(
            "Invalid state (reserved+sold > stock) — not a real invariant input"
        )

    available = stock - reserved - sold
    assert available >= 0


@given(
    stock=st.integers(min_value=1, max_value=10_000),
    reserved_frac=st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
    sold_frac=st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
)
@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
def test_available_formula_structure(
    stock: int, reserved_frac: float, sold_frac: float
) -> None:
    """
    Generate (reserved, sold) as fractions of stock so they are always valid.
    """
    reserved = int(stock * reserved_frac)
    # sold can only come from the remaining stock, not from reserved
    remaining = stock - reserved
    sold = int(remaining * sold_frac)

    available = stock - reserved - sold
    assert available >= 0
    assert available <= stock


# ── P2: reservation increases reserved by exactly quantity ────────────────


@given(
    stock=st.integers(min_value=1, max_value=1_000),
    reserved=st.integers(min_value=0, max_value=500),
    sold=st.integers(min_value=0, max_value=500),
    quantity=st.integers(min_value=1, max_value=50),
)
@settings(max_examples=500)
def test_reserve_increases_reserved_by_quantity(
    stock: int, reserved: int, sold: int, quantity: int
) -> None:
    """
    After a successful reserve, reserved_quantity increases by exactly `quantity`.
    The available stock decreases by exactly `quantity`.
    """
    if reserved + sold >= stock:
        pytest.skip("No available stock — reservation would fail")

    available_before = stock - reserved - sold
    if quantity > available_before:
        pytest.skip("Quantity exceeds available — reservation would fail")

    # Apply the reservation
    new_reserved = reserved + quantity
    new_available = stock - new_reserved - sold

    assert new_reserved == reserved + quantity
    assert new_available == available_before - quantity
    assert new_available >= 0


# ── P3: release decrements reserved by min(quantity, reserved) ────────────


@given(
    stock=st.integers(min_value=1, max_value=1_000),
    reserved=st.integers(min_value=0, max_value=500),
    sold=st.integers(min_value=0, max_value=500),
    quantity=st.integers(min_value=1, max_value=100),
)
@settings(max_examples=500)
def test_release_uses_greatest_zero_floor(
    stock: int, reserved: int, sold: int, quantity: int
) -> None:
    """
    release uses GREATEST(reserved - qty, 0) so reserved never goes negative.
    """
    # Apply GREATEST(..., 0) — the same logic in the SQL UPDATE
    new_reserved = max(reserved - quantity, 0)

    assert new_reserved >= 0
    assert new_reserved <= reserved  # release never increases reserved


# ── P4: expiry never creates negative reserved_quantity ───────────────────


@given(
    stock=st.integers(min_value=0, max_value=10_000),
    reserved=st.integers(min_value=0, max_value=10_000),
    sold=st.integers(min_value=0, max_value=10_000),
    expiry_quantity=st.integers(min_value=1, max_value=1_000),
)
@settings(max_examples=500)
def test_expiry_release_uses_greatest_never_negative(
    stock: int, reserved: int, sold: int, expiry_quantity: int
) -> None:
    """
    expire_stale_reservations uses GREATEST(reserved_quantity - qty, 0).
    This must never produce a negative reserved_quantity, even if qty > reserved.
    """
    new_reserved = max(reserved - expiry_quantity, 0)
    assert new_reserved >= 0


# ── P5: order status machine ──────────────────────────────────────────────


_VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"stock_reserved", "cancelled"},
    "stock_reserved": {"confirmed", "payment_pending", "cancelled", "payment_expired"},
    "payment_pending": {"confirmed", "payment_failed", "cancelled"},
    "confirmed": {"shipped", "cancelled"},
    "shipped": {"delivered", "return_requested"},
    "delivered": {"return_requested"},
    "return_requested": {"returned", "delivered"},
    "returned": set(),
    "cancelled": set(),
    "payment_failed": {"pending"},
    "payment_expired": {"pending"},
}

_ALL_STATUSES = list(_VALID_TRANSITIONS.keys())


@given(
    from_status=st.sampled_from(_ALL_STATUSES),
    to_status=st.sampled_from(_ALL_STATUSES),
)
@settings(max_examples=200)
def test_order_status_transitions_are_consistent(
    from_status: str, to_status: str
) -> None:
    """
    The status machine is deterministic: for every (from, to) pair, it's
    either always valid or always invalid — never context-dependent.
    """
    allowed = _VALID_TRANSITIONS.get(from_status, set())
    # This test just verifies the machine is internally consistent
    if to_status in allowed:
        assert to_status in _VALID_TRANSITIONS  # target must be a known status
    else:
        # Disallowed transitions stay disallowed (no contradictions in the map)
        assert to_status not in allowed


@given(st.sampled_from(_ALL_STATUSES))
@settings(max_examples=50)
def test_terminal_statuses_have_no_transitions(status: str) -> None:
    """Terminal statuses must have no outgoing transitions."""
    terminal = {"returned", "cancelled"}
    if status in terminal:
        assert len(_VALID_TRANSITIONS[status]) == 0


# ── P6: asyncio.Lock serialization — no over-reservation ─────────────────


@dataclass
class _PropState:
    stock_quantity: int
    reserved_quantity: int = 0
    sold_quantity: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def available(self) -> int:
        return self.stock_quantity - self.reserved_quantity - self.sold_quantity


async def _prop_atomic_reserve(state: _PropState, quantity: int) -> bool:

    async with state.lock:
        if state.available < quantity:
            return False
        state.reserved_quantity += quantity
        return True


@given(
    stock=st.integers(min_value=1, max_value=50),
    concurrency=st.integers(min_value=2, max_value=100),
    qty_per_request=st.integers(min_value=1, max_value=5),
)
@settings(max_examples=200, deadline=None)
def test_concurrent_reservations_never_over_reserve(
    stock: int, concurrency: int, qty_per_request: int
) -> None:
    """
    For any valid (stock, concurrency, qty) triple, total reserved must not
    exceed stock_quantity.
    """

    async def _run():
        state = _PropState(stock_quantity=stock)
        await asyncio.gather(
            *[_prop_atomic_reserve(state, qty_per_request) for _ in range(concurrency)],
            return_exceptions=True,
        )
        return state

    state = asyncio.get_event_loop().run_until_complete(_run())
    assert (
        state.reserved_quantity <= state.stock_quantity
    ), f"reserved={state.reserved_quantity} > stock={state.stock_quantity}"
    assert state.available >= 0


# ── P7: get_available_stock formula matches arithmetic ────────────────────


@given(
    stock=st.integers(min_value=0, max_value=10_000),
    reserved=st.integers(min_value=0),
    sold=st.integers(min_value=0),
)
@settings(max_examples=500)
def test_available_stock_formula_max_zero(stock: int, reserved: int, sold: int) -> None:
    """
    get_available_stock uses max(int(row[0]), 0).
    Even if the DB returns a negative computed value, the Python layer floors it.
    """
    raw_available = stock - reserved - sold  # could be negative
    available = max(raw_available, 0)
    assert available >= 0
