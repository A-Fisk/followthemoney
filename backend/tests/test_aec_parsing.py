"""
Unit tests for pure parsing functions in ingest_aec.py.
No database or network required.
"""

import sys
from decimal import Decimal
from pathlib import Path

# Add scripts/ to path so we can import without installing
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from ingest_aec import normalise_party_name, normalise_donor_name, parse_amount


class TestNormalisePartyName:
    def test_canonical_passthrough(self):
        assert normalise_party_name("Australian Labor Party") == "Australian Labor Party"

    def test_lowercase_alias(self):
        assert normalise_party_name("alp") == "Australian Labor Party"

    def test_messy_aec_suffix(self):
        # AEC sometimes includes "(ALP)" in party names
        assert normalise_party_name("Australian Labor Party (ALP)") == "Australian Labor Party"

    def test_state_branch_stripped(self):
        assert normalise_party_name("Australian Greens (ACT Branch)") == "Australian Greens"

    def test_greens_variants(self):
        assert normalise_party_name("the greens") == "Australian Greens"
        assert normalise_party_name("Greens") == "Australian Greens"

    def test_nationals_variants(self):
        assert normalise_party_name("National Party of Australia") == "The Nationals"
        assert normalise_party_name("nationals") == "The Nationals"

    def test_unknown_party_passthrough(self):
        # Unknown parties are returned as-is (title stripped but otherwise unchanged)
        assert normalise_party_name("  Some Minor Party  ") == "Some Minor Party"


class TestNormaliseDonorName:
    def test_all_caps_to_title(self):
        assert normalise_donor_name("MINERALOGY PTY LTD") == "Mineralogy PTY LTD"

    def test_mixed_case_normalised(self):
        assert normalise_donor_name("mineralogy pty ltd") == "Mineralogy PTY LTD"

    def test_abbreviations_preserved_upper(self):
        name = normalise_donor_name("HANCOCK PROSPECTING PTY LTD")
        assert "PTY" in name
        assert "LTD" in name

    def test_state_abbreviation_preserved(self):
        assert normalise_donor_name("labor NSW") == "Labor NSW"

    def test_extra_whitespace_collapsed(self):
        assert normalise_donor_name("  BHP   Group  ") == "Bhp Group"

    def test_idempotent(self):
        once = normalise_donor_name("SOME DONOR PTY LTD")
        twice = normalise_donor_name(once)
        assert once == twice


class TestParseAmount:
    def test_plain_integer(self):
        assert parse_amount("10000") == Decimal("10000")

    def test_comma_separated(self):
        assert parse_amount("1,234,567") == Decimal("1234567")

    def test_decimal(self):
        assert parse_amount("9999.99") == Decimal("9999.99")

    def test_empty_string(self):
        assert parse_amount("") is None

    def test_whitespace_only(self):
        assert parse_amount("   ") is None

    def test_non_numeric(self):
        assert parse_amount("N/A") is None

    def test_zero(self):
        assert parse_amount("0") == Decimal("0")
