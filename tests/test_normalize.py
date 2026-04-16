"""Tests for extension name normalization."""

import pytest
from riscv_explorer.normalize import normalize_tag, normalize_tags, strip_arch_prefix


class TestStripArchPrefix:
    def test_rv_prefix(self):
        assert strip_arch_prefix("rv_i") == "i"

    def test_rv32_prefix(self):
        assert strip_arch_prefix("rv32_zknd") == "zknd"

    def test_rv64_prefix(self):
        assert strip_arch_prefix("rv64_zba") == "zba"

    def test_unknown_prefix_raises(self):
        with pytest.raises(ValueError, match="unknown tag format"):
            strip_arch_prefix("x_zba")

    def test_no_prefix_raises(self):
        with pytest.raises(ValueError):
            strip_arch_prefix("zba")


class TestNormalizeTag:
    # ── Single-extension tags ─────────────────────────────────────────────────

    def test_base_integer(self):
        assert normalize_tag("rv_i") == ("I",)

    def test_single_letter_extensions(self):
        assert normalize_tag("rv_m") == ("M",)
        assert normalize_tag("rv_a") == ("A",)
        assert normalize_tag("rv_f") == ("F",)
        assert normalize_tag("rv_d") == ("D",)
        assert normalize_tag("rv_c") == ("C",)
        assert normalize_tag("rv_h") == ("H",)

    def test_zba_extension(self):
        assert normalize_tag("rv_zba") == ("Zba",)

    def test_zicsr_extension(self):
        assert normalize_tag("rv_zicsr") == ("Zicsr",)

    def test_zifencei_extension(self):
        assert normalize_tag("rv_zifencei") == ("Zifencei",)

    def test_long_z_extension(self):
        assert normalize_tag("rv_zvkned") == ("Zvkned",)

    # ── Arch-variant collapsing ───────────────────────────────────────────────

    def test_rv_and_rv64_collapse(self):
        # Both must produce the exact same result
        assert normalize_tag("rv_zba") == normalize_tag("rv64_zba")

    def test_rv32_and_rv64_zknd_collapse(self):
        assert normalize_tag("rv32_zknd") == normalize_tag("rv64_zknd") == ("Zknd",)

    def test_rv64_m(self):
        assert normalize_tag("rv64_m") == ("M",)

    # ── Compound tags ─────────────────────────────────────────────────────────

    def test_compound_c_f(self):
        result = set(normalize_tag("rv_c_f"))
        assert result == {"C", "F"}

    def test_compound_c_f_32bit(self):
        result = set(normalize_tag("rv32_c_f"))
        assert result == {"C", "F"}

    def test_compound_c_d(self):
        result = set(normalize_tag("rv_c_d"))
        assert result == {"C", "D"}

    def test_compound_d_zfa(self):
        result = set(normalize_tag("rv32_d_zfa"))
        assert result == {"D", "Zfa"}

    def test_compound_q_zfa(self):
        result = set(normalize_tag("rv64_q_zfa"))
        assert result == {"Q", "Zfa"}

    def test_compound_zfh_zfa(self):
        result = set(normalize_tag("rv_zfh_zfa"))
        assert result == {"Zfh", "Zfa"}

    def test_compound_zabha_zacas(self):
        result = set(normalize_tag("rv_zabha_zacas"))
        assert result == {"Zabha", "Zacas"}

    def test_compound_d_zfhmin(self):
        result = set(normalize_tag("rv_d_zfhmin"))
        assert result == {"D", "Zfhmin"}

    # ── Privilege extensions — must NOT be split ──────────────────────────────

    def test_smrnmi_not_split(self):
        # "sm" prefix signals a single Machine-level extension
        assert normalize_tag("rv_smrnmi") == ("Smrnmi",)

    def test_ssctr_not_split(self):
        # "ss" prefix signals a single Supervisor extension
        assert normalize_tag("rv_ssctr") == ("Ssctr",)

    def test_svinval_not_split(self):
        # "sv" prefix — Svinval is a single extension
        assert normalize_tag("rv_svinval") == ("Svinval",)

    def test_sdext_not_split(self):
        assert normalize_tag("rv_sdext") == ("Sdext",)

    # ── Override cases ────────────────────────────────────────────────────────

    def test_svinval_h_override(self):
        # svinval_h must be split despite "sv" prefix — explicit override
        result = set(normalize_tag("rv_svinval_h"))
        assert result == {"Svinval", "H"}

    # ── Return type is always tuple ───────────────────────────────────────────

    def test_returns_tuple(self):
        result = normalize_tag("rv_i")
        assert isinstance(result, tuple)

    def test_compound_returns_tuple(self):
        result = normalize_tag("rv_c_f")
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestNormalizeTags:
    def test_single_tag_list(self):
        result = normalize_tags(["rv_i"])
        assert result == frozenset({"I"})

    def test_arch_variants_deduplicated(self):
        # rv_zba and rv64_zba both normalize to Zba — frozenset size must be 1
        result = normalize_tags(["rv_zba", "rv64_zba"])
        assert result == frozenset({"Zba"})
        assert len(result) == 1

    def test_multiple_distinct_extensions(self):
        result = normalize_tags(["rv32_zknd", "rv32_zk", "rv32_zkn"])
        assert result == frozenset({"Zknd", "Zk", "Zkn"})

    def test_compound_tag_in_list(self):
        result = normalize_tags(["rv_c_f"])
        assert result == frozenset({"C", "F"})

    def test_empty_list(self):
        assert normalize_tags([]) == frozenset()

    def test_returns_frozenset(self):
        assert isinstance(normalize_tags(["rv_i"]), frozenset)
