"""CompanyConfigOut and CompanyConfigUpdate schema unit tests."""

from unittest.mock import MagicMock

import pytest


class TestCompanyConfigOut:
    def setup_method(self):
        from app.modules.company.schemas import CompanyConfigOut

        self.schema = CompanyConfigOut

    def test_all_fields_populated(self):
        data = self.schema(
            name="Hadha",
            tagline="Shop local",
            gstin="29ABCDE1234F1Z5",
            city="Hyderabad",
            state="Telangana",
            postal_code="500001",
            country="IN",
            phone="+919876543210",
            support_email="support@hadha.co",
            website="https://hadha.co",
            logo_url="https://hadha.co/logo.png",
            packing_slip_logo_url="https://hadha.co/packing-slip-logo.png",
            shipping_label_logo_url="https://hadha.co/shipping-label-logo.png",
            instagram_url="https://instagram.com/hadha",
            facebook_url="https://facebook.com/hadha",
        )
        assert data.name == "Hadha"
        assert data.city == "Hyderabad"
        assert data.instagram_url == "https://instagram.com/hadha"

    def test_only_required_fields_nullable_as_none(self):
        data = self.schema(
            name="Hadha",
            country="IN",
            tagline=None,
            gstin=None,
            city=None,
            state=None,
            postal_code=None,
            phone=None,
            support_email=None,
            website=None,
            logo_url=None,
            packing_slip_logo_url=None,
            shipping_label_logo_url=None,
            instagram_url=None,
            facebook_url=None,
        )
        assert data.name == "Hadha"
        assert data.country == "IN"
        assert data.tagline is None
        assert data.city is None

    def test_raises_validation_error_when_name_missing(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            self.schema(country="IN")

    def test_raises_validation_error_when_country_missing(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            self.schema(name="Hadha")

    def test_from_attributes_works_with_orm_mock(self):
        mock_obj = MagicMock()
        mock_obj.name = "Hadha"
        mock_obj.tagline = "Shop local"
        mock_obj.gstin = None
        mock_obj.city = "Hyderabad"
        mock_obj.state = None
        mock_obj.postal_code = None
        mock_obj.country = "IN"
        mock_obj.phone = None
        mock_obj.support_email = None
        mock_obj.website = None
        mock_obj.logo_url = None
        mock_obj.packing_slip_logo_url = None
        mock_obj.shipping_label_logo_url = None
        mock_obj.instagram_url = None
        mock_obj.facebook_url = None

        data = self.schema.model_validate(mock_obj)
        assert data.name == "Hadha"
        assert data.city == "Hyderabad"
        assert data.country == "IN"

    def test_rejects_country_longer_than_two_chars(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            self.schema(
                name="Hadha",
                tagline=None,
                gstin=None,
                city=None,
                state=None,
                postal_code=None,
                country="India",
                phone=None,
                support_email=None,
                website=None,
                logo_url=None,
                packing_slip_logo_url=None,
                shipping_label_logo_url=None,
                instagram_url=None,
                facebook_url=None,
            )


class TestCompanyConfigUpdate:
    def setup_method(self):
        from app.modules.company.schemas import CompanyConfigUpdate

        self.schema = CompanyConfigUpdate

    def test_no_args_creates_empty_update_all_none(self):
        data = self.schema()
        assert data.name is None
        assert data.country is None
        assert data.city is None

    def test_partial_fields_sets_only_those_fields(self):
        data = self.schema(name="Hadha", city="Hyderabad")
        assert data.name == "Hadha"
        assert data.city == "Hyderabad"
        assert data.country is None
        assert data.phone is None

    @pytest.mark.parametrize(
        "field",
        [
            "name",
            "tagline",
            "gstin",
            "city",
            "state",
            "postal_code",
            # "country" excluded — it's a 2-char ISO code, see dedicated tests below.
            "phone",
            "support_email",
            "website",
            "logo_url",
            "packing_slip_logo_url",
            "shipping_label_logo_url",
            "instagram_url",
            "facebook_url",
        ],
    )
    def test_each_field_can_be_set_independently(self, field):
        data = self.schema(**{field: "test_value"})
        assert getattr(data, field) == "test_value"

    def test_country_can_be_set_independently(self):
        data = self.schema(country="US")
        assert data.country == "US"

    def test_country_normalizes_to_uppercase(self):
        data = self.schema(country="in")
        assert data.country == "IN"

    def test_country_rejects_values_longer_than_two_chars(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            self.schema(country="India")

    def test_model_dump_includes_all_fields(self):
        data = self.schema(name="Hadha")
        dumped = data.model_dump()

        expected_keys = {
            "name",
            "tagline",
            "gstin",
            "city",
            "state",
            "postal_code",
            "country",
            "phone",
            "support_email",
            "website",
            "logo_url",
            "packing_slip_logo_url",
            "shipping_label_logo_url",
            "instagram_url",
            "facebook_url",
        }
        assert expected_keys == set(dumped.keys())
        assert dumped["name"] == "Hadha"
        assert dumped["city"] is None
