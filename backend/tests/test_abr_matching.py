"""
Unit tests for pick_best_match in enrich_abr.py.
No database or network required.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from enrich_abr import pick_best_match


class TestPickBestMatch:
    def test_exact_match_wins(self):
        matches = [
            {"Name": "Hancock Prospecting Pty Ltd", "Abn": "111"},
            {"Name": "Hancock Group", "Abn": "222"},
        ]
        result = pick_best_match("Hancock Prospecting Pty Ltd", matches)
        assert result is not None
        assert result["Abn"] == "111"

    def test_exact_match_case_insensitive(self):
        matches = [{"Name": "BHP GROUP PTY LTD", "Abn": "333"}]
        result = pick_best_match("BHP Group Pty Ltd", matches)
        assert result is not None
        assert result["Abn"] == "333"

    def test_single_result_returned_even_without_exact_match(self):
        matches = [{"Name": "Rio Tinto Operations", "Abn": "444"}]
        result = pick_best_match("Rio Tinto", matches)
        assert result is not None
        assert result["Abn"] == "444"

    def test_multiple_non_exact_returns_none(self):
        matches = [
            {"Name": "Santos Ltd", "Abn": "555"},
            {"Name": "Santos Operations", "Abn": "666"},
        ]
        result = pick_best_match("Santos", matches)
        assert result is None

    def test_empty_matches_returns_none(self):
        assert pick_best_match("Anyone", []) is None

    def test_multiple_exact_matches_returns_single(self):
        # If there's exactly one exact match, return it even if there are others
        matches = [
            {"Name": "Exact Name", "Abn": "777"},
            {"Name": "Exact Name", "Abn": "888"},  # duplicate — ambiguous
        ]
        # Two exact matches → ambiguous → None
        result = pick_best_match("Exact Name", matches)
        assert result is None
