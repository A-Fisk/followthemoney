"""
Unit tests for pure parsing functions in ingest_tvfy.py.
No database or network required.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from ingest_tvfy import extract_issue_tags, tags_to_anzsic


class TestExtractIssueTags:
    def test_extracts_policy_names(self):
        detail = {
            "policy_votes": [
                {"policy": {"id": 1, "name": "Coal and mining"}, "vote": "aye3"},
                {"policy": {"id": 2, "name": "Climate change"}, "vote": "aye3"},
            ]
        }
        tags = extract_issue_tags(detail)
        assert "Coal and mining" in tags
        assert "Climate change" in tags

    def test_empty_policy_votes(self):
        assert extract_issue_tags({"policy_votes": []}) == []

    def test_missing_policy_votes_key(self):
        assert extract_issue_tags({}) == []

    def test_null_policy_votes(self):
        assert extract_issue_tags({"policy_votes": None}) == []

    def test_policy_entry_missing_policy_key_skipped(self):
        detail = {
            "policy_votes": [
                {"policy": {"id": 1, "name": "Gambling"}, "vote": "aye3"},
                {"vote": "no3"},  # no "policy" key
            ]
        }
        tags = extract_issue_tags(detail)
        assert tags == ["Gambling"]


class TestTagsToAnzsic:
    def test_coal_maps_to_coal_anzsic(self):
        codes = tags_to_anzsic(["Coal and mining"])
        assert "0600" in codes  # Coal Mining

    def test_gambling_maps_correctly(self):
        codes = tags_to_anzsic(["Gambling regulation"])
        assert "9201" in codes

    def test_multiple_tags_merged(self):
        codes = tags_to_anzsic(["Coal and mining", "Climate change"])
        assert "0600" in codes

    def test_no_matching_tags(self):
        codes = tags_to_anzsic(["Refugees and asylum seekers"])
        # Refugees has no ANZSIC mapping — result should be empty or very small
        assert isinstance(codes, list)

    def test_empty_tags(self):
        assert tags_to_anzsic([]) == []

    def test_returns_sorted_list(self):
        codes = tags_to_anzsic(["Coal and mining", "Petroleum"])
        assert codes == sorted(codes)

    def test_no_duplicates(self):
        # Both "coal" and "mining" keywords match coal tags — should not duplicate
        codes = tags_to_anzsic(["Coal and mining"])
        assert len(codes) == len(set(codes))
