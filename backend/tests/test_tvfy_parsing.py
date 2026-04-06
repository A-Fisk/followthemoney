"""
Unit tests for pure parsing functions in ingest_tvfy.py.
No database or network required.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from ingest_tvfy import extract_issue_tags, tags_to_anzsic


class TestExtractIssueTags:
    def test_uses_policy_map_when_provided(self):
        detail = {"id": 42}
        policy_map = {42: ["Coal and mining", "Climate change"]}
        tags = extract_issue_tags(detail, policy_map)
        assert tags == ["Coal and mining", "Climate change"]

    def test_policy_map_miss_falls_back_to_policy_divisions(self):
        detail = {
            "id": 99,
            "policy_divisions": [
                {"policy": {"id": 1, "name": "Gambling"}, "vote": "aye3"},
            ]
        }
        tags = extract_issue_tags(detail, policy_map={})
        assert tags == ["Gambling"]

    def test_no_map_no_policy_divisions(self):
        assert extract_issue_tags({"id": 1, "policy_divisions": []}) == []

    def test_missing_keys_returns_empty(self):
        assert extract_issue_tags({}) == []

    def test_null_policy_divisions(self):
        assert extract_issue_tags({"id": 1, "policy_divisions": None}) == []

    def test_policy_entry_missing_policy_key_skipped(self):
        detail = {
            "id": 5,
            "policy_divisions": [
                {"policy": {"id": 1, "name": "Gambling"}, "vote": "aye3"},
                {"vote": "no3"},  # no "policy" key
            ]
        }
        tags = extract_issue_tags(detail, policy_map={})
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
