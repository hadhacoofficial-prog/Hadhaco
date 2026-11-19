import pytest
from pydantic import ValidationError

from app.modules.catalog.schemas import ProductCreateRequest, ProductUpdateRequest

_BASE = {"sku": "SKU-1", "name": "Ring", "slug": "ring", "base_price": 100}


def test_new_products_default_to_non_returnable():
    product = ProductCreateRequest(**_BASE)
    assert product.is_returnable is False
    assert product.return_window_days is None


def test_returnable_product_accepts_window():
    product = ProductCreateRequest(**_BASE, is_returnable=True, return_window_days=10)
    assert product.is_returnable is True
    assert product.return_window_days == 10


@pytest.mark.parametrize("days", [0, -1, 366])
def test_window_outside_1_to_365_rejected(days):
    with pytest.raises(ValidationError):
        ProductCreateRequest(**_BASE, return_window_days=days)
    with pytest.raises(ValidationError):
        ProductUpdateRequest(return_window_days=days)


def test_update_leaves_policy_unset_when_omitted():
    patch = ProductUpdateRequest(name="Ring 2")
    assert patch.model_dump(exclude_unset=True) == {"name": "Ring 2"}


def test_label_defaults_to_none_and_blank_becomes_none():
    assert ProductCreateRequest(**_BASE).return_policy_label is None
    blank = ProductCreateRequest(**_BASE, return_policy_label="   ")
    assert blank.return_policy_label is None
    assert ProductUpdateRequest(return_policy_label="").return_policy_label is None


def test_label_is_trimmed_and_length_limited():
    product = ProductCreateRequest(
        **_BASE, return_policy_label="  Easy {days}-day returns "
    )
    assert product.return_policy_label == "Easy {days}-day returns"
    with pytest.raises(ValidationError):
        ProductCreateRequest(**_BASE, return_policy_label="x" * 101)
    with pytest.raises(ValidationError):
        ProductUpdateRequest(return_policy_label="x" * 101)
