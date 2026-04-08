"""
Unit tests for nickname-matching logic in merge_politicians.py.
No database or network required.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from merge_politicians import normalise_first_name, NICKNAME_MAP, _NICKNAME_TO_FORMAL


class TestNormaliseFirstName:
    def test_formal_name_returns_unchanged(self):
        assert normalise_first_name("James") == "James"

    def test_nickname_maps_to_formal(self):
        assert normalise_first_name("Jim") == "James"
        assert normalise_first_name("Bob") == "Robert"

    def test_case_insensitive_lookup(self):
        assert normalise_first_name("jim") == "James"
        assert normalise_first_name("JIM") == "James"
        assert normalise_first_name("BOB") == "Robert"

    def test_unknown_name_returned_as_is(self):
        assert normalise_first_name("Xavier") == "Xavier"
        assert normalise_first_name("Barnaby") == "Barnaby"

    def test_tony_maps_to_anthony(self):
        assert normalise_first_name("Tony") == "Anthony"

    def test_bill_maps_to_william(self):
        assert normalise_first_name("Bill") == "William"

    def test_formal_name_in_nickname_list_is_canonical(self):
        # "Robert" is the formal name — should come back as "Robert"
        assert normalise_first_name("Robert") == "Robert"

    def test_whitespace_stripped(self):
        assert normalise_first_name("  Jim  ") == "James"

    def test_australian_political_names(self):
        # The specific cases that motivated this issue
        assert normalise_first_name("Jim") == "James"    # Jim/James Chalmers
        assert normalise_first_name("Bob") == "Robert"   # Bob/Robert Katter


class TestNicknameMapConsistency:
    def test_all_formal_names_are_title_case(self):
        for formal in NICKNAME_MAP:
            assert formal == formal.title() or formal[0].isupper(), (
                f"{formal!r} should be title-cased"
            )

    def test_no_nickname_maps_to_two_different_formals(self):
        # Each nickname should map to exactly one canonical form
        seen: dict[str, str] = {}
        for formal, nicks in NICKNAME_MAP.items():
            for nick in nicks:
                key = nick.lower()
                if key in seen:
                    assert seen[key] == formal, (
                        f"Nickname {nick!r} maps to both {seen[key]!r} and {formal!r}"
                    )
                seen[key] = formal

    def test_reverse_map_covers_all_nicknames(self):
        for formal, nicks in NICKNAME_MAP.items():
            for nick in nicks:
                assert nick.lower() in _NICKNAME_TO_FORMAL, (
                    f"Nickname {nick!r} (for {formal}) missing from reverse map"
                )

    def test_formal_name_not_in_reverse_map_as_nickname(self):
        # A formal name should not appear as a nickname for a different formal name
        for formal in NICKNAME_MAP:
            other_formals = {k for k in NICKNAME_MAP if k != formal}
            for other_formal in other_formals:
                assert formal not in NICKNAME_MAP[other_formal], (
                    f"{formal!r} appears as a nickname for {other_formal!r}"
                )


class TestNicknameVariantDetection:
    """
    Tests for the logic used in Pass 3 to identify variant pairs.
    We test the normalise_first_name function as a proxy for the matching logic,
    since the DB query part requires a live connection.
    """

    def _is_variant_pair(self, name_a: str, name_b: str) -> bool:
        """Return True if name_a and name_b are nickname variants of each other."""
        first_a = name_a.strip().split()[0]
        first_b = name_b.strip().split()[0]
        last_a = name_a.strip().split()[-1].lower()
        last_b = name_b.strip().split()[-1].lower()
        if last_a != last_b:
            return False
        if first_a.lower() == first_b.lower():
            return False
        return normalise_first_name(first_a) == normalise_first_name(first_b)

    def test_jim_james_chalmers_are_variants(self):
        assert self._is_variant_pair("Jim Chalmers", "James Chalmers")

    def test_bob_robert_katter_are_variants(self):
        assert self._is_variant_pair("Bob Katter", "Robert Katter")

    def test_different_last_name_not_matched(self):
        assert not self._is_variant_pair("Jim Chalmers", "James Smith")

    def test_different_unrelated_first_names_not_matched(self):
        assert not self._is_variant_pair("Anthony Smith", "James Smith")

    def test_identical_names_not_flagged_as_variants(self):
        # Same first name — not a nickname variant situation
        assert not self._is_variant_pair("James Smith", "James Smith")

    def test_tony_anthony_are_variants(self):
        assert self._is_variant_pair("Tony Abbott", "Anthony Abbott")

    def test_bill_william_are_variants(self):
        assert self._is_variant_pair("Bill Shorten", "William Shorten")

    def test_unknown_names_not_matched(self):
        assert not self._is_variant_pair("Barnaby Joyce", "Xavier Joyce")
