"""Unit tests for _logo_data_uri and _register_unicode_font helpers
in app.modules.fulfillment.service — no real filesystem or reportlab calls."""

import base64
from unittest.mock import MagicMock, patch


class TestLogoDataUri:
    def _call(self):
        from app.modules.fulfillment.service import _logo_data_uri

        return _logo_data_uri()

    def test_returns_string_starting_with_data_uri_prefix_when_file_exists(self):
        fake_bytes = b"PNG_CONTENT"
        with patch("pathlib.Path.read_bytes", return_value=fake_bytes):
            result = self._call()

        assert result is not None
        assert result.startswith("data:image/png;base64,")

    def test_returns_none_when_file_not_found_error(self):
        with patch("pathlib.Path.read_bytes", side_effect=FileNotFoundError):
            result = self._call()

        assert result is None

    def test_returns_none_when_any_exception_raised(self):
        with patch("pathlib.Path.read_bytes", side_effect=OSError("disk error")):
            result = self._call()

        assert result is None

    def test_correctly_base64_encodes_known_bytes(self):
        known_bytes = b"\x89PNG\r\n\x1a\n"
        expected_b64 = base64.b64encode(known_bytes).decode()

        with patch("pathlib.Path.read_bytes", return_value=known_bytes):
            result = self._call()

        assert result == f"data:image/png;base64,{expected_b64}"


class TestRegisterUnicodeFont:
    def _call(self):
        from app.modules.fulfillment.service import _register_unicode_font

        return _register_unicode_font()

    def _patch_pdfmetrics(self, registered_names=None, register_side_effect=None):
        """Return a context manager that patches the pdfmetrics and TTFont imports."""
        mock_pdfmetrics = MagicMock()
        mock_pdfmetrics.getRegisteredFontNames.return_value = (
            registered_names if registered_names is not None else []
        )
        if register_side_effect is not None:
            mock_pdfmetrics.registerFont.side_effect = register_side_effect

        mock_ttfont_cls = MagicMock()

        import unittest.mock as _mock

        return (
            _mock.patch.multiple(
                "app.modules.fulfillment.service",
                # The function imports these locally — patch via sys.modules instead.
            ),
            mock_pdfmetrics,
            mock_ttfont_cls,
        )

    def test_returns_true_immediately_if_already_registered(self):
        mock_pdfmetrics = MagicMock()
        mock_pdfmetrics.getRegisteredFontNames.return_value = ["HadhaUni", "Helvetica"]

        with patch(
            "reportlab.pdfbase.pdfmetrics.getRegisteredFontNames",
            mock_pdfmetrics.getRegisteredFontNames,
        ):
            with patch("reportlab.pdfbase.pdfmetrics.registerFont"):
                with patch("pathlib.Path.exists", return_value=False):
                    result = self._call()

        assert result is True

    def test_registers_font_and_returns_true_when_first_candidate_exists(self):
        mock_pdfmetrics = MagicMock()
        mock_pdfmetrics.getRegisteredFontNames.return_value = []

        with patch(
            "reportlab.pdfbase.pdfmetrics.getRegisteredFontNames",
            mock_pdfmetrics.getRegisteredFontNames,
        ):
            with patch("reportlab.pdfbase.pdfmetrics.registerFont") as mock_register:
                with patch("pathlib.Path.exists", return_value=True):
                    with patch(
                        "reportlab.pdfbase.ttfonts.TTFont", return_value=MagicMock()
                    ):
                        result = self._call()

        assert result is True
        assert mock_register.called

    def test_returns_false_when_no_candidate_paths_exist(self):
        mock_pdfmetrics = MagicMock()
        mock_pdfmetrics.getRegisteredFontNames.return_value = []

        with patch(
            "reportlab.pdfbase.pdfmetrics.getRegisteredFontNames",
            mock_pdfmetrics.getRegisteredFontNames,
        ):
            with patch("reportlab.pdfbase.pdfmetrics.registerFont"):
                with patch("pathlib.Path.exists", return_value=False):
                    result = self._call()

        assert result is False

    def test_skips_failing_candidates_and_tries_next(self):
        """First candidate path raises on registerFont; second succeeds → True."""
        mock_pdfmetrics = MagicMock()
        mock_pdfmetrics.getRegisteredFontNames.return_value = []

        call_count = {"n": 0}

        def register_side_effect(font):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise Exception("bad font")
            # second call succeeds silently

        with patch(
            "reportlab.pdfbase.pdfmetrics.getRegisteredFontNames",
            mock_pdfmetrics.getRegisteredFontNames,
        ):
            with patch(
                "reportlab.pdfbase.pdfmetrics.registerFont",
                side_effect=register_side_effect,
            ):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch(
                        "reportlab.pdfbase.ttfonts.TTFont",
                        return_value=MagicMock(),
                    ):
                        result = self._call()

        assert result is True
        assert call_count["n"] == 2

    def test_returns_false_when_all_candidates_fail_with_exceptions(self):
        mock_pdfmetrics = MagicMock()
        mock_pdfmetrics.getRegisteredFontNames.return_value = []

        with patch(
            "reportlab.pdfbase.pdfmetrics.getRegisteredFontNames",
            mock_pdfmetrics.getRegisteredFontNames,
        ):
            with patch(
                "reportlab.pdfbase.pdfmetrics.registerFont",
                side_effect=Exception("font broken"),
            ):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch(
                        "reportlab.pdfbase.ttfonts.TTFont",
                        return_value=MagicMock(),
                    ):
                        result = self._call()

        assert result is False
