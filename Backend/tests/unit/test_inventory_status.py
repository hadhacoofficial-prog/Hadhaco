from app.modules.inventory.status import (
    InventoryStatus,
    compute_available_stock,
    compute_inventory_status,
)


class TestComputeAvailableStock:
    def test_normal_case(self):
        assert compute_available_stock(10, 3, 2) == 5

    def test_zero_after_subtraction(self):
        assert compute_available_stock(5, 3, 2) == 0

    def test_negative_clamps_to_zero(self):
        assert compute_available_stock(5, 4, 4) == 0

    def test_all_zero(self):
        assert compute_available_stock(0, 0, 0) == 0

    def test_reserved_and_sold_exceed_stock(self):
        assert compute_available_stock(2, 5, 5) == 0


class TestComputeInventoryStatus:
    def test_in_stock_above_threshold(self):
        status, can_purchase = compute_inventory_status(10, 5, True, False)
        assert status == InventoryStatus.IN_STOCK
        assert can_purchase is True

    def test_low_stock_at_threshold_boundary(self):
        # available == threshold is still LOW_STOCK, not IN_STOCK
        status, can_purchase = compute_inventory_status(5, 5, True, False)
        assert status == InventoryStatus.LOW_STOCK
        assert can_purchase is True

    def test_in_stock_just_above_threshold_boundary(self):
        status, can_purchase = compute_inventory_status(6, 5, True, False)
        assert status == InventoryStatus.IN_STOCK
        assert can_purchase is True

    def test_low_stock_between_zero_and_threshold(self):
        status, can_purchase = compute_inventory_status(1, 5, True, False)
        assert status == InventoryStatus.LOW_STOCK
        assert can_purchase is True

    def test_out_of_stock_zero_available_no_backorder(self):
        status, can_purchase = compute_inventory_status(0, 5, True, False)
        assert status == InventoryStatus.OUT_OF_STOCK
        assert can_purchase is False

    def test_out_of_stock_negative_available_no_backorder(self):
        # available_stock is expected to already be floored at 0 by callers,
        # but the function itself must not crash or misclassify negative input.
        status, can_purchase = compute_inventory_status(-3, 5, True, False)
        assert status == InventoryStatus.OUT_OF_STOCK
        assert can_purchase is False

    def test_zero_stock_with_backorder_stays_purchasable(self):
        # Backorder-eligible products present as IN_STOCK — the spec only
        # allows 3 customer-visible states, backorder isn't one of them.
        status, can_purchase = compute_inventory_status(0, 5, True, True)
        assert status == InventoryStatus.IN_STOCK
        assert can_purchase is True

    def test_track_inventory_false_always_in_stock(self):
        # Untracked products are always purchasable regardless of counters.
        status, can_purchase = compute_inventory_status(0, 5, False, False)
        assert status == InventoryStatus.IN_STOCK
        assert can_purchase is True

    def test_zero_threshold_only_out_of_stock_at_zero(self):
        status, can_purchase = compute_inventory_status(1, 0, True, False)
        assert status == InventoryStatus.IN_STOCK
        assert can_purchase is True
