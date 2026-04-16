"""
Extension name normalization.

instr_dict.json uses tags like rv_i, rv64_zba, rv32_zknd, rv_c_f.
The ISA manual uses Zba, I, Zknd, C, F, etc.

This module bridges that gap. The tricky part: rv_c_f means "C+F compound"
(instructions that exist at the intersection) while rv_smrnmi means "Smrnmi"
as a single extension name — even though both have the same structural shape
after stripping the prefix.
"""

# Two-character prefixes that mark a single privileged/platform extension.
# An extension body starting with one of these is never split into parts.
# See: https://github.com/riscv/riscv-isa-manual/blob/main/src/naming.adoc
_PRIV_PREFIXES: frozenset[str] = frozenset({"sm", "ss", "sv", "sh", "sd"})

# A handful of tags that look compound by the underscore rule but need
# manual overrides because the first part starts with a priv prefix.
# Key: the body after stripping the arch prefix (e.g., "svinval_h").
_COMPOUND_OVERRIDES: dict[str, tuple[str, ...]] = {
    "svinval_h": ("Svinval", "H"),
}

_ARCH_PREFIXES = ("rv32_", "rv64_", "rv_")


def strip_arch_prefix(tag: str) -> str:
    """
    Remove the leading arch qualifier from a raw extension tag.

    "rv32_zknd"  -> "zknd"
    "rv64_zba"   -> "zba"
    "rv_i"       -> "i"

    Raises ValueError for tags that don't start with a recognised prefix.
    """
    for prefix in _ARCH_PREFIXES:
        if tag.startswith(prefix):
            return tag[len(prefix):]
    raise ValueError(f"unknown tag format: {tag!r}")


def _capitalize(part: str) -> str:
    """
    Title-case a single extension name component.

    Single letters become uppercase; multi-char names get first-letter-up
    and the rest lowercased.  "zba" -> "Zba", "i" -> "I", "zicsr" -> "Zicsr".
    """
    if not part:
        raise ValueError("empty extension component")
    return part[0].upper() + part[1:].lower()


def normalize_tag(tag: str) -> tuple[str, ...]:
    """
    Map one raw tag to a tuple of canonical extension names.

    Returns a tuple (always, even for single-extension results) so callers
    can treat every result uniformly with a simple iteration.

    Examples
    --------
    normalize_tag("rv_i")          -> ("I",)
    normalize_tag("rv_zba")        -> ("Zba",)
    normalize_tag("rv64_zba")      -> ("Zba",)   # same as rv_zba
    normalize_tag("rv32_zknd")     -> ("Zknd",)
    normalize_tag("rv_c_f")        -> ("C", "F")
    normalize_tag("rv32_c_f")      -> ("C", "F")
    normalize_tag("rv_c_d")        -> ("C", "D")
    normalize_tag("rv32_d_zfa")    -> ("D", "Zfa")
    normalize_tag("rv_svinval_h")  -> ("Svinval", "H")
    normalize_tag("rv_smrnmi")     -> ("Smrnmi",)
    normalize_tag("rv_ssctr")      -> ("Ssctr",)
    """
    body = strip_arch_prefix(tag)

    # Explicit overrides take priority — these are bodies that look compound
    # by the underscore rule but have a non-mechanical mapping.
    if body in _COMPOUND_OVERRIDES:
        return _COMPOUND_OVERRIDES[body]

    # No underscore in the body → always a single extension name.
    if "_" not in body:
        return (_capitalize(body),)

    # Body has underscores.  Check whether it's a single privileged extension
    # (e.g., "smrnmi", "ssctr", "svinval") that just happens to start with a
    # two-letter platform prefix.  These are never split.
    if body[:2] in _PRIV_PREFIXES:
        return (_capitalize(body),)

    # Otherwise treat each underscore-separated segment as a distinct
    # extension name.  "c_f" -> ("C", "F"),  "d_zfhmin" -> ("D", "Zfhmin").
    return tuple(_capitalize(part) for part in body.split("_"))


def normalize_tags(tags: list[str]) -> frozenset[str]:
    """
    Normalize a list of raw tags (as stored in the JSON "extension" field)
    to a flat frozenset of canonical extension names.

    The frozenset automatically de-duplicates arch variants that map to the
    same canonical name, so ["rv_zba", "rv64_zba"] -> frozenset({"Zba"}).
    """
    result: set[str] = set()
    for tag in tags:
        result.update(normalize_tag(tag))
    return frozenset(result)
