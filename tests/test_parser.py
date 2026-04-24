"""Tests for instruction parsing and grouping (Tier 1)."""

import json
from pathlib import Path

import pytest

from riscv_explorer.parser import (
    group_by_canonical_extension,
    find_multi_extension_instructions,
    build_summary,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_instr_dict.json"


@pytest.fixture
def sample_dict():
    return json.loads(FIXTURE.read_text())


class TestGroupByCanonicalExtension:
    def test_basic_grouping(self, sample_dict):
        groups = group_by_canonical_extension(sample_dict)
        assert "I" in groups
        assert "add" in groups["I"]

    def test_arch_variant_merged_to_single_group(self, sample_dict):
        # sh1add uses rv_zba, add_uw uses rv64_zba — both must land in Zba
        groups = group_by_canonical_extension(sample_dict)
        assert "Zba" in groups
        assert "add_uw" in groups["Zba"]
        assert "sh1add" in groups["Zba"]

    def test_compound_tag_appears_in_both_groups(self, sample_dict):
        groups = group_by_canonical_extension(sample_dict)
        # fld has rv_c_d -> appears in both C and D
        assert "fld" in groups.get("C", [])
        assert "fld" in groups.get("D", [])

    def test_compound_32bit_tag(self, sample_dict):
        # flw has rv32_c_f -> appears in both C and F
        groups = group_by_canonical_extension(sample_dict)
        assert "flw" in groups.get("C", [])
        assert "flw" in groups.get("F", [])

    def test_privilege_extension_single_group(self, sample_dict):
        # mnret has rv_smrnmi -> exactly one group, Smrnmi
        groups = group_by_canonical_extension(sample_dict)
        assert "Smrnmi" in groups
        assert "mnret" in groups["Smrnmi"]
        # Should NOT appear in any other group
        for ext, mnemonics in groups.items():
            if ext != "Smrnmi":
                assert "mnret" not in mnemonics

    def test_svinval_h_split(self, sample_dict):
        # hinval_gvma has rv_svinval_h -> Svinval and H
        groups = group_by_canonical_extension(sample_dict)
        assert "hinval_gvma" in groups.get("Svinval", [])
        assert "hinval_gvma" in groups.get("H", [])

    def test_output_sorted_by_extension_name(self, sample_dict):
        groups = group_by_canonical_extension(sample_dict)
        keys = list(groups.keys())
        assert keys == sorted(keys)

    def test_mnemonics_sorted_within_group(self, sample_dict):
        groups = group_by_canonical_extension(sample_dict)
        for ext, mnemonics in groups.items():
            assert mnemonics == sorted(mnemonics), f"{ext} mnemonics not sorted"


class TestFindMultiExtensionInstructions:
    def test_crypto_instr_found(self, sample_dict):
        multi = find_multi_extension_instructions(sample_dict)
        mnemonics = [m.mnemonic for m in multi]
        assert "aes32dsi" in mnemonics
        assert "aes64ds" in mnemonics

    def test_andn_found(self, sample_dict):
        multi = find_multi_extension_instructions(sample_dict)
        mnemonics = [m.mnemonic for m in multi]
        assert "andn" in mnemonics

    def test_arch_variants_not_counted_as_multi(self, sample_dict):
        # mulw has only rv64_m -> canonical {M}, size 1 -> must NOT appear
        multi = find_multi_extension_instructions(sample_dict)
        assert "mulw" not in [m.mnemonic for m in multi]

    def test_single_extension_not_counted(self, sample_dict):
        # add has only rv_i -> single canonical -> must NOT appear
        multi = find_multi_extension_instructions(sample_dict)
        assert "add" not in [m.mnemonic for m in multi]

    def test_compound_tag_counts_as_multi(self, sample_dict):
        # fld has rv_c_d -> {C, D} size 2 -> IS multi
        multi = find_multi_extension_instructions(sample_dict)
        mnemonics = [m.mnemonic for m in multi]
        assert "fld" in mnemonics

    def test_result_sorted_by_mnemonic(self, sample_dict):
        multi = find_multi_extension_instructions(sample_dict)
        names = [m.mnemonic for m in multi]
        assert names == sorted(names)

    def test_canonical_extensions_is_frozenset(self, sample_dict):
        multi = find_multi_extension_instructions(sample_dict)
        for item in multi:
            assert isinstance(item.canonical_extensions, frozenset)


class TestBuildSummary:
    def test_total_instructions(self, sample_dict):
        summary = build_summary(sample_dict)
        assert summary.total_instructions == len(sample_dict)

    def test_total_canonical_extensions(self, sample_dict):
        summary = build_summary(sample_dict)
        # canonical_groups merges arch variants — must be <= raw tag count
        assert len(summary.canonical_groups) > 10

    def test_raw_tag_count_gte_canonical(self, sample_dict):
        summary = build_summary(sample_dict)
        # raw tags include arch variants (rv_zba, rv64_zba) so always >= canonical
        assert len(summary.raw_tag_groups) >= len(summary.canonical_groups)

    def test_raw_tags_present(self, sample_dict):
        summary = build_summary(sample_dict)
        assert "rv_i" in summary.raw_tag_groups
        assert "rv64_zba" in summary.raw_tag_groups

    def test_canonical_groups_present(self, sample_dict):
        summary = build_summary(sample_dict)
        assert "I" in summary.canonical_groups
        assert "Zba" in summary.canonical_groups

    def test_multi_ext_present(self, sample_dict):
        summary = build_summary(sample_dict)
        assert len(summary.multi_ext) > 0
