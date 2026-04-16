"""
Tier 2 — Cross-Reference with the ISA Manual.

Clones the official riscv-isa-manual repository (shallow, depth=1) and scans
all AsciiDoc source files for extension name references.  The results are then
compared against the canonical extension set derived from instr_dict.json.

Why clone instead of hitting the GitHub API?
  - The API has aggressive rate limits for unauthenticated requests.
  - There are 80+ .adoc files spread across three subdirectories; fetching them
    one by one over HTTP is slow and brittle.
  - A shallow clone (~15 s on first run) grabs everything at once and is then
    cached indefinitely under ~/.cache/riscv-explorer/isa-manual/.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich import box

from .parser import SummaryData

ISA_MANUAL_URL = "https://github.com/riscv/riscv-isa-manual.git"

console = Console()

# ── Regex patterns for extracting extension names from AsciiDoc ──────────────
#
# Four syntactic forms appear in the wild (verified against the actual repo):
#
#   1. ext:zba[]  or  extlink:zbb[]           — most common, new-style macro
#   2. "Zba" or `Zbkb` in section headers     — title lines starting with =
#   3. [[ext:zicsr]]                           — new-style anchor
#   4. [[zbkb-sc,Zbkb]]                        — old-style anchor, readable form after comma
#   5. <<#zba>>  or  <<zba>>                  — AsciiDoc cross-reference (very common
#                                               for bitmanip: Zba, Zbc, Zbs all use this)
#
# Pattern 2 is intentionally restricted to header lines (starting with =) to
# avoid false positives from normal prose like "The M extension..."
#
# Single-letter extensions (I, M, A, F, D, Q, C, H, V) use ext:i[] which requires
# the regex to accept zero additional chars: [a-z][a-z0-9]{0,20} not {1,20}.
#
# Platform-prefix shorthands (ext:sm[], ext:sh[]) appear in the priv spec as
# collective references and are filtered out — they're not standalone extension names.

_RE_EXT_MACRO = re.compile(r"\bext(?:link)?:([a-z][a-z0-9]{0,20})\b")
_RE_HEADER_QUOTED = re.compile(r'(?:"|`)([A-Z][a-zA-Z0-9]{0,20})(?:"|`)')
_RE_ANCHOR_EXT = re.compile(r"\[\[ext:([a-z][a-z0-9]{0,20})\]\]")
_RE_ANCHOR_COMMA = re.compile(r"\[\[[^\]]+,([A-Z][a-zA-Z0-9]{0,20})\]\]")
# AsciiDoc cross-references: <<#zba>>, <<zba>>, <<zba,some label>>
# Pattern is intentionally restrictive — only extension-shaped anchors:
#   Z-prefixed (zba, zbb, zicsr, ...)  /  X-prefixed experimental  /
#   single-letter base ISA (i, m, a, f, d, q, c, h, v, e) alone (no suffix) /
#   S-prefixed platform exts with a 2-letter prefix + at least 3 more chars,
#   so that CSR names like "satp", "scause", "sstatus" don't match.
_RE_XREF = re.compile(
    r"<<#?("
    r"z[a-z][a-z0-9]{0,18}"                    # Z-prefixed standard extensions
    r"|x[a-z][a-z0-9]{0,18}"                   # X-prefixed experimental
    r"|[acdefghimqv](?=[,>])"                  # Single-letter base ISA only if followed by , or >
    r"|(?:sm|ss|sv|sh|sd)[a-z][a-z0-9]{1,17}" # S-prefixed platform (smepmp, svinval, ...)
    r")(?:,.*?)?>>"
)

# Two-letter platform-prefix shorthands that appear as ext:sm[], ext:ss[], etc.
# These are collective references ("all Sm* extensions"), not standalone extension names.
_PLATFORM_PREFIX_SHORTHANDS: frozenset[str] = frozenset({
    "sm", "ss", "sv", "sh", "sd", "su",
})

# Common false positives in anchor/header context that are not extension names.
_NOISE_WORDS: frozenset[str] = frozenset({
    "ISA", "ABI", "CSR", "PC", "RV", "RISC", "RISC-V", "EEI", "AEE",
    "Table", "Figure", "Appendix", "NOTE", "TODO", "WARL", "WLRL",
    "SAIL", "IEEE", "ELEN", "VLEN", "MLEN", "SEW", "LMUL", "VLMAX",
})


def clone_isa_manual(
    repo_url: str = ISA_MANUAL_URL,
    cache_dir: Path | None = None,
) -> Path:
    """
    Clone the ISA manual with --depth 1 into cache_dir.

    If the target directory already has a .git folder the clone is skipped
    and the cached path is returned immediately (subsequent runs are instant).

    cache_dir defaults to ~/.cache/riscv-explorer/isa-manual.
    """
    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "riscv-explorer" / "isa-manual"

    if (cache_dir / ".git").exists():
        console.print(
            f"[dim]ISA manual already cached at {cache_dir}[/dim]"
        )
        return cache_dir

    cache_dir.parent.mkdir(parents=True, exist_ok=True)

    with console.status(f"Cloning ISA manual (this happens once)..."):
        result = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(cache_dir)],
            capture_output=True,
            text=True,
        )

    if result.returncode != 0:
        raise RuntimeError(
            f"git clone failed:\n{result.stderr}"
        )

    console.print("[green]✓[/green] ISA manual cloned")
    return cache_dir


def scan_adoc_file(path: Path) -> set[str]:
    """
    Extract extension name references from a single .adoc file.

    Returns a set of lowercase names (e.g., {"zba", "zbb", "m", "zicsr"}).
    False positives are reduced by:
      - restricting the quoted-name pattern to header lines (starting with =)
      - filtering against a noise-word blocklist
      - filtering out known platform-prefix shorthands (sm, ss, sv, sh, su)
        that appear as collective references in the priv spec (e.g., ext:sm[])
        rather than as actual standalone extension names
    """
    found: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return found

    for line in text.splitlines():
        # Pattern 1: ext:name[] or extlink:name[] anywhere on the line.
        # {0,20} (not {1,20}) so single-letter base extensions like ext:i[],
        # ext:m[], ext:a[] are captured.
        for m in _RE_EXT_MACRO.finditer(line):
            name = m.group(1).lower()
            if name not in _PLATFORM_PREFIX_SHORTHANDS:
                found.add(name)

        # Pattern 3: [[ext:name]] anchors anywhere
        for m in _RE_ANCHOR_EXT.finditer(line):
            found.add(m.group(1).lower())

        # Pattern 4: [[something,Name]] anchors — the readable name after comma
        for m in _RE_ANCHOR_COMMA.finditer(line):
            name = m.group(1)
            if name not in _NOISE_WORDS:
                found.add(name.lower())

        # Pattern 5: <<#zba>> or <<zba>> AsciiDoc cross-references.
        # This is the primary way Zba, Zbc, Zbs are referenced in b-st-ext.adoc.
        for m in _RE_XREF.finditer(line):
            found.add(m.group(1).lower())

        # Pattern 2: "Name" or `Name` but ONLY in header lines (lines with =).
        # Restricted to headers to avoid capturing random capitalized words in prose.
        if line.lstrip().startswith("="):
            for m in _RE_HEADER_QUOTED.finditer(line):
                name = m.group(1)
                if name not in _NOISE_WORDS and len(name) >= 1:
                    found.add(name.lower())

    return found


def scan_isa_manual(repo_root: Path) -> dict[str, set[str]]:
    """
    Walk all .adoc files under repo_root/src/ and scan each one.

    Returns a mapping of relative file path -> set of found extension names.
    """
    src_dir = repo_root / "src"
    if not src_dir.exists():
        raise FileNotFoundError(f"Expected src/ directory at {src_dir}")

    adoc_files = sorted(src_dir.rglob("*.adoc"))
    results: dict[str, set[str]] = {}

    with console.status(f"Scanning {len(adoc_files)} .adoc files..."):
        for adoc in adoc_files:
            rel = str(adoc.relative_to(repo_root))
            found = scan_adoc_file(adoc)
            if found:
                results[rel] = found

    console.print(
        f"[green]✓[/green] Scanned {len(adoc_files)} files, "
        f"found references in {len(results)}"
    )
    return results


def build_manual_extension_set(scan_results: dict[str, set[str]]) -> set[str]:
    """Flatten all per-file sets into one deduplicated set of lowercase names."""
    combined: set[str] = set()
    for names in scan_results.values():
        combined.update(names)
    return combined


@dataclass
class CrossRefReport:
    matched: set[str] = field(default_factory=set)
    json_only: set[str] = field(default_factory=set)
    manual_only: set[str] = field(default_factory=set)
    total_json: int = 0
    total_manual_raw: int = 0


def cross_reference(
    summary: SummaryData,
    manual_exts: set[str],
) -> CrossRefReport:
    """
    Compare canonical extension names from the JSON against manual references.

    Matching is case-insensitive: "Zba" from JSON matches "zba" from the manual.
    """
    # Canonical names from JSON (lowercase for comparison)
    json_canonical = set(summary.groups.keys())
    json_lower = {name.lower(): name for name in json_canonical}

    # Manual extensions are already lowercase from scan_adoc_file
    manual_lower = manual_exts

    matched_lower = json_lower.keys() & manual_lower
    json_only_lower = json_lower.keys() - manual_lower
    # Manual mentions that don't correspond to any JSON extension
    manual_only_lower = manual_lower - json_lower.keys()

    # Restore canonical casing for display
    matched = {json_lower[k] for k in matched_lower}
    json_only = {json_lower[k] for k in json_only_lower}
    # Manual-only names: capitalize first letter for readability
    manual_only = {
        k[0].upper() + k[1:] for k in manual_only_lower
        if len(k) >= 1 and k.isalpha()  # filter out noise/numbers
    }

    return CrossRefReport(
        matched=matched,
        json_only=json_only,
        manual_only=manual_only,
        total_json=len(json_canonical),
        total_manual_raw=len(manual_lower),
    )


def print_cross_ref_report(report: CrossRefReport) -> None:
    def _fmt(names: set[str]) -> str:
        return ", ".join(sorted(names)) if names else "—"

    table = Table(
        title="Cross-Reference Report",
        box=box.DOUBLE_EDGE,
        header_style="bold cyan",
        show_lines=True,
    )
    table.add_column("Category", style="bold", min_width=14)
    table.add_column("Count", justify="right", min_width=6)
    table.add_column("Extensions", overflow="fold")

    table.add_row(
        "[green]Matched[/green]",
        str(len(report.matched)),
        _fmt(report.matched),
    )
    table.add_row(
        "[yellow]JSON only[/yellow]",
        str(len(report.json_only)),
        _fmt(report.json_only),
    )
    table.add_row(
        "[red]Manual only[/red]",
        str(len(report.manual_only)),
        _fmt(report.manual_only),
    )

    console.print(table)
    console.print(
        f"\n  [bold]{len(report.matched)} matched[/bold], "
        f"[yellow]{len(report.json_only)} in JSON only[/yellow], "
        f"[red]{len(report.manual_only)} in manual only[/red]\n"
    )
    if report.json_only:
        console.print(
            "  [dim]Note: JSON-only extensions are typically privilege/platform "
            "extensions (Sm*, Ss*, Sv*) defined in the privileged spec, not covered "
            "by the unprivileged ISA manual scan.[/dim]\n"
        )
