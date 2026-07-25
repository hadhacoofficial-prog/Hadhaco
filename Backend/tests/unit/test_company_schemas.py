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
            legal_name="Hadha Jewels Pvt Ltd",
            brand_name="Hadha",
            tagline="Shop local",
            description="Fine jewellery",
            website="https://hadha.co",
            domain="hadha.co",
            logo_url="https://hadha.co/logo.png",
            favicon_url="https://hadha.co/favicon.ico",
            packing_slip_logo_url="https://hadha.co/packing-slip-logo.png",
            shipping_label_logo_url="https://hadha.co/shipping-label-logo.png",
            phone="+919876543210",
            alternate_phone="+911234567890",
            whatsapp="+919876543210",
            support_email="support@hadha.co",
            sales_email="sales@hadha.co",
            address_line_1="123 Main St",
            address_line_2="Suite 4",
            city="Hyderabad",
            state="Telangana",
            postal_code="500001",
            country="IN",
            google_maps_url="https://maps.google.com",
            latitude=17.385,
            longitude=78.4867,
            gstin="29ABCDE1234F1Z5",
            cin="U52399TG2020PTC144847",
            business_hours="Mon-Sat 10AM-8PM",
            instagram_url="https://instagram.com/hadha",
            facebook_url="https://facebook.com/hadha",
            youtube_url="https://youtube.com/hadha",
            twitter_x_url="https://x.com/hadha",
            linkedin_url="https://linkedin.com/hadha",
            pinterest_url="https://pinterest.com/hadha",
            default_meta_title="Hadha Jewellery",
            default_meta_description="Fine jewellery store",
            organization_description="Hadha is a fine jewellery brand",
            theme_color="#C9A96E",
        )
        assert data.name == "Hadha"
        assert data.city == "Hyderabad"
        assert data.instagram_url == "https://instagram.com/hadha"
        assert data.theme_color == "#C9A96E"

    def test_only_required_fields_nullable_as_none(self):
        data = self.schema(
            name="Hadha",
            country="IN",
            legal_name=None,
            brand_name=None,
            tagline=None,
            description=None,
            website=None,
            domain=None,
            logo_url=None,
            favicon_url=None,
            packing_slip_logo_url=None,
            shipping_label_logo_url=None,
            phone=None,
            alternate_phone=None,
            whatsapp=None,
            support_email=None,
            sales_email=None,
            address_line_1=None,
            address_line_2=None,
            city=None,
            state=None,
            postal_code=None,
            google_maps_url=None,
            latitude=None,
            longitude=None,
            gstin=None,
            cin=None,
            business_hours=None,
            instagram_url=None,
            facebook_url=None,
            youtube_url=None,
            twitter_x_url=None,
            linkedin_url=None,
            pinterest_url=None,
            default_meta_title=None,
            default_meta_description=None,
            organization_description=None,
            theme_color=None,
        )
        assert data.name == "Hadha"
        assert data.country == "IN"
        assert data.tagline is None
        assert data.city is None
        assert data.theme_color is None

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
        mock_obj.legal_name = None
        mock_obj.brand_name = None
        mock_obj.tagline = "Shop local"
        mock_obj.description = None
        mock_obj.website = None
        mock_obj.domain = None
        mock_obj.logo_url = None
        mock_obj.favicon_url = None
        mock_obj.packing_slip_logo_url = None
        mock_obj.shipping_label_logo_url = None
        mock_obj.phone = None
        mock_obj.alternate_phone = None
        mock_obj.whatsapp = None
        mock_obj.support_email = None
        mock_obj.sales_email = None
        mock_obj.address_line_1 = None
        mock_obj.address_line_2 = None
        mock_obj.city = "Hyderabad"
        mock_obj.state = None
        mock_obj.postal_code = None
        mock_obj.country = "IN"
        mock_obj.google_maps_url = None
        mock_obj.latitude = None
        mock_obj.longitude = None
        mock_obj.gstin = None
        mock_obj.cin = None
        mock_obj.business_hours = None
        mock_obj.instagram_url = None
        mock_obj.facebook_url = None
        mock_obj.youtube_url = None
        mock_obj.twitter_x_url = None
        mock_obj.linkedin_url = None
        mock_obj.pinterest_url = None
        mock_obj.default_meta_title = None
        mock_obj.default_meta_description = None
        mock_obj.organization_description = None
        mock_obj.theme_color = None

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
                cin=None,
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
                youtube_url=None,
                twitter_x_url=None,
                linkedin_url=None,
                pinterest_url=None,
                legal_name=None,
                brand_name=None,
                description=None,
                domain=None,
                favicon_url=None,
                alternate_phone=None,
                whatsapp=None,
                sales_email=None,
                address_line_1=None,
                address_line_2=None,
                google_maps_url=None,
                latitude=None,
                longitude=None,
                business_hours=None,
                default_meta_title=None,
                default_meta_description=None,
                organization_description=None,
                theme_color=None,
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
            "legal_name",
            "brand_name",
            "tagline",
            "description",
            "website",
            "domain",
            "logo_url",
            "favicon_url",
            "packing_slip_logo_url",
            "shipping_label_logo_url",
            "phone",
            "alternate_phone",
            "whatsapp",
            "support_email",
            "sales_email",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "postal_code",
            # "country" excluded — it's a 2-char ISO code, see dedicated tests below.
            # "latitude", "longitude" excluded — float, not str; tested separately.
            "google_maps_url",
            "gstin",
            "cin",
            "business_hours",
            "instagram_url",
            "facebook_url",
            "youtube_url",
            "twitter_x_url",
            "linkedin_url",
            "pinterest_url",
            "default_meta_title",
            "default_meta_description",
            "organization_description",
            "theme_color",
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

    def test_latitude_can_be_set_independently(self):
        data = self.schema(latitude=17.385)
        assert data.latitude == 17.385

    def test_longitude_can_be_set_independently(self):
        data = self.schema(longitude=78.4867)
        assert data.longitude == 78.4867

    def test_model_dump_includes_all_fields(self):
        data = self.schema(name="Hadha")
        dumped = data.model_dump()

        expected_keys = {
            "name",
            "legal_name",
            "brand_name",
            "tagline",
            "description",
            "website",
            "domain",
            "logo_url",
            "favicon_url",
            "packing_slip_logo_url",
            "shipping_label_logo_url",
            "phone",
            "alternate_phone",
            "whatsapp",
            "support_email",
            "sales_email",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "postal_code",
            "country",
            "google_maps_url",
            "latitude",
            "longitude",
            "gstin",
            "cin",
            "business_hours",
            "instagram_url",
            "facebook_url",
            "youtube_url",
            "twitter_x_url",
            "linkedin_url",
            "pinterest_url",
            "default_meta_title",
            "default_meta_description",
            "organization_description",
            "theme_color",
        }
        assert expected_keys == set(dumped.keys())
        assert dumped["name"] == "Hadha"
        assert dumped["city"] is None
        assert dumped["theme_color"] is None
