"""Tests for ISA manual scanning and cross-reference logic (Tier 2)."""

import tempfile
from pathlib import Path

import pytest

from riscv_explorer.cross_ref import scan_adoc_file, build_manual_extension_set, cross_reference
from riscv_explorer.parser import SummaryData


def make_adoc(content: str) -> Path:
    """Write content to a temporary .adoc file and return its path."""
    tmp = tempfile.NamedTemporaryFile(
        suffix=".adoc", mode="w", delete=False, encoding="utf-8"
    )
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


class TestScanAdocFile:
    def test_ext_macro_detected(self):
        p = make_adoc("The ext:zba[] extension depends on ext:zbb[].")
        result = scan_adoc_file(p)
        assert "zba" in result
        assert "zbb" in result

    def test_extlink_macro_detected(self):
        p = make_adoc("See extlink:zicsr[] for details.")
        result = scan_adoc_file(p)
        assert "zicsr" in result

    def test_anchor_ext_style_detected(self):
        p = make_adoc("[[ext:zicsr]]\n=== Zicsr extension")
        result = scan_adoc_file(p)
        assert "zicsr" in result

    def test_comma_anchor_detected(self):
        p = make_adoc("[[zbkb-sc,Zbkb]]\n==== Some section")
        result = scan_adoc_file(p)
        assert "zbkb" in result

    def test_quoted_name_in_header_detected(self):
        p = make_adoc('=== "M" Extension for Integer Multiplication\nSome text.')
        result = scan_adoc_file(p)
        assert "m" in result

    def test_backtick_name_in_header_detected(self):
        p = make_adoc("==== `Zbkb` - Bit manipulation\nSome prose.")
        result = scan_adoc_file(p)
        assert "zbkb" in result

    def test_quoted_name_in_prose_not_detected(self):
        # "Table" and "Figure" are in _NOISE_WORDS; other words in prose
        # body lines (no leading =) should not be captured.
        p = make_adoc('Some prose with "Normal" capitalized words and "Table".')
        result = scan_adoc_file(p)
        # Neither should appear as extension names
        assert "normal" not in result
        assert "table" not in result

    def test_multiple_patterns_same_file(self):
        content = (
            "[[ext:zba]]\n"
            '=== "Zba" Extension\n'
            "This depends on ext:zbb[] and ext:zbs[].\n"
            "[[zbkb-sc,Zbkb]]\n"
        )
        p = make_adoc(content)
        result = scan_adoc_file(p)
        assert "zba" in result
        assert "zbb" in result
        assert "zbs" in result
        assert "zbkb" in result

    def test_results_are_lowercase(self):
        p = make_adoc("=== `Zbkb` Extension\next:ZBA[] present")
        result = scan_adoc_file(p)
        # All results must be lowercase
        for name in result:
            assert name == name.lower(), f"{name!r} is not lowercase"

    def test_empty_file(self):
        p = make_adoc("")
        result = scan_adoc_file(p)
        assert isinstance(result, set)


class TestBuildManualExtensionSet:
    def test_flattens_multiple_files(self):
        scan_results = {
            "src/zba.adoc": {"zba", "zbb"},
            "src/scalar-crypto.adoc": {"zbkb", "zbkc", "zk"},
        }
        result = build_manual_extension_set(scan_results)
        assert result == {"zba", "zbb", "zbkb", "zbkc", "zk"}

    def test_deduplicates(self):
        scan_results = {
            "src/a.adoc": {"zba", "zbb"},
            "src/b.adoc": {"zba", "zbc"},  # zba appears in both
        }
        result = build_manual_extension_set(scan_results)
        assert len([x for x in result if x == "zba"]) == 1

    def test_empty_input(self):
        assert build_manual_extension_set({}) == set()


class TestCrossReference:
    def _make_summary(self, extensions: list[str]) -> SummaryData:
        canonical_groups = {ext: ["dummy"] for ext in extensions}
        return SummaryData(
            canonical_groups=canonical_groups,
            multi_ext=[],
            total_instructions=len(extensions),
        )

    def test_matched_set(self):
        summary = self._make_summary(["Zba", "Zbb", "I"])
        manual = {"zba", "zbb", "m"}
        report = cross_reference(summary, manual)
        assert "Zba" in report.matched
        assert "Zbb" in report.matched

    def test_json_only(self):
        summary = self._make_summary(["Zba", "Smrnmi"])
        manual = {"zba"}
        report = cross_reference(summary, manual)
        assert "Smrnmi" in report.json_only
        assert "Zba" not in report.json_only

    def test_manual_only(self):
        summary = self._make_summary(["Zba"])
        manual = {"zba", "zawrs", "zihintpause"}
        report = cross_reference(summary, manual)
        # zawrs and zihintpause are in manual but not in JSON
        manual_only_lower = {n.lower() for n in report.manual_only}
        assert "zawrs" in manual_only_lower or "Zawrs" in report.manual_only
        assert "Zba" not in report.json_only

    def test_case_insensitive_matching(self):
        # JSON has "Zba" (capitalized); manual has "zba" (lowercase)
        summary = self._make_summary(["Zba"])
        manual = {"zba"}
        report = cross_reference(summary, manual)
        assert "Zba" in report.matched
        assert len(report.json_only) == 0
