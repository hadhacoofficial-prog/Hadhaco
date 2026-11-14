"""get_razorpay_client: one shared client whose HTTP calls always time out."""

from unittest.mock import patch


class TestRazorpayClient:
    def setup_method(self):
        from app.core.security import get_razorpay_client

        get_razorpay_client.cache_clear()

    def teardown_method(self):
        from app.core.security import get_razorpay_client

        get_razorpay_client.cache_clear()

    def test_client_is_reused(self):
        from app.core.security import get_razorpay_client

        assert get_razorpay_client() is get_razorpay_client()

    def test_session_applies_default_timeout(self):
        from app.core.security import RAZORPAY_HTTP_TIMEOUT, get_razorpay_client

        session = get_razorpay_client().session
        with patch("requests.Session.request") as base_request:
            session.post("https://api.razorpay.com/v1/orders")
            assert base_request.call_args.kwargs["timeout"] == RAZORPAY_HTTP_TIMEOUT

            session.post("https://api.razorpay.com/v1/orders", timeout=3)
            assert base_request.call_args.kwargs["timeout"] == 3
