"""
Unit tests for pure parsing functions in ingest_register.py.
No database or network required.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from ingest_register import extract_provider, extract_date, parse_iso_date


class TestExtractProvider:
    def test_provided_by(self):
        assert extract_provider("Provided by Qantas Airways.") == "Qantas Airways"

    def test_sponsored_by(self):
        assert extract_provider("Sponsored by BHP Group.") == "BHP Group"

    def test_hosted_by(self):
        assert extract_provider("Hosted by the Mining Council.") == "the Mining Council"

    def test_from_pattern(self):
        assert extract_provider("Flight from Gina Rinehart - return Perth to Sydney") == "Gina Rinehart"

    def test_courtesy_of(self):
        assert extract_provider("Travel courtesy of Rio Tinto.") == "Rio Tinto"

    def test_no_match_returns_none(self):
        assert extract_provider("Attended a conference in Canberra.") is None

    def test_trailing_punctuation_stripped(self):
        result = extract_provider("Provided by Santos Ltd,")
        assert result is not None
        assert not result.endswith(",")


class TestExtractDate:
    def test_dd_mm_yyyy_slash(self):
        assert extract_date("Event on 15/03/2023") == date(2023, 3, 15)

    def test_dd_mm_yyyy_dash(self):
        assert extract_date("Received 01-06-2024") == date(2024, 6, 1)

    def test_dd_mm_yy_short_year(self):
        assert extract_date("Date: 05/11/24") == date(2024, 11, 5)

    def test_no_date_returns_none(self):
        assert extract_date("No date in this text at all.") is None

    def test_invalid_date_returns_none(self):
        # 32nd day — invalid
        assert extract_date("On 32/01/2023") is None


class TestParseIsoDate:
    def test_iso_date_only(self):
        assert parse_iso_date("2023-06-15") == date(2023, 6, 15)

    def test_iso_datetime(self):
        assert parse_iso_date("2023-06-15T10:30:00") == date(2023, 6, 15)

    def test_iso_datetime_with_z(self):
        assert parse_iso_date("2023-06-15T10:30:00Z") == date(2023, 6, 15)

    def test_senate_api_format(self):
        # The Senate API returns "8/11/2025 2:00:00 PM" (M/D/YYYY)
        assert parse_iso_date("8/11/2025 2:00:00 PM") == date(2025, 8, 11)

    def test_senate_api_format_single_digits(self):
        assert parse_iso_date("1/5/2024 9:00:00 AM") == date(2024, 1, 5)

    def test_empty_string_returns_none(self):
        assert parse_iso_date("") is None

    def test_none_returns_none(self):
        assert parse_iso_date(None) is None

    def test_with_timezone_offset(self):
        # Should strip timezone and return the date portion
        assert parse_iso_date("2023-06-15T10:30:00+10:00") == date(2023, 6, 15)
