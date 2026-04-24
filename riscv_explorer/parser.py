"""
Tier 1 — Instruction Set Parsing.

Fetches instr_dict.json, groups instructions by extension tag, and identifies
instructions that belong to more than one extension.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

import requests
from rich.console import Console
from rich.table import Table
from rich import box

from .normalize import normalize_tags

INSTR_DICT_URL = (
    "https://raw.githubusercontent.com/rpsene/riscv-extensions-landscape"
    "/main/src/instr_dict.json"
)

console = Console()


class InstrEntry(TypedDict):
    encoding: str
    variable_fields: list[str]
    extension: list[str]
    match: str
    mask: str


@dataclass
class MultiExtInstr:
    mnemonic: str
    raw_tags: list[str]
    canonical_extensions: frozenset[str]


@dataclass
class SummaryData:
    # raw extension tag -> sorted list of mnemonics  (matches the JSON structure)
    raw_tag_groups: dict[str, list[str]] = field(default_factory=dict)
    # canonical extension name -> sorted list of mnemonics  (arch variants merged)
    canonical_groups: dict[str, list[str]] = field(default_factory=dict)
    multi_ext: list[MultiExtInstr] = field(default_factory=list)
    total_instructions: int = 0


def fetch_instr_dict(
    url: str = INSTR_DICT_URL,
    cache_path: Path | None = None,
) -> dict[str, InstrEntry]:
    """
    Fetch the instruction dictionary JSON.

    If cache_path is given and the file exists, read from disk.
    If cache_path is given but the file doesn't exist, download and save it.
    """
    if cache_path is not None and cache_path.exists():
        return json.loads(cache_path.read_text())

    with console.status("Fetching instruction dictionary..."):
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()

    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data, indent=2))

    console.print(f"[green]✓[/green] Fetched {len(data)} instructions")
    return data


def group_by_raw_tag(
    instr_dict: dict[str, InstrEntry],
) -> dict[str, list[str]]:
    """
    Build a mapping from raw extension tag to sorted list of mnemonics.

    This preserves the original tag names from the JSON (rv_zba, rv64_zba, etc.)
    exactly as the source data records them.  An instruction with multiple tags
    (e.g., andn with rv_zbb, rv_zk, rv_zbkb, ...) appears in each tag's group.
    """
    groups: dict[str, list[str]] = {}
    for mnemonic, entry in instr_dict.items():
        for tag in entry.get("extension", []):
            groups.setdefault(tag, []).append(mnemonic)
    return dict(sorted({k: sorted(v) for k, v in groups.items()}.items()))


def group_by_canonical_extension(
    instr_dict: dict[str, InstrEntry],
) -> dict[str, list[str]]:
    """
    Build a mapping from canonical extension name to sorted list of mnemonics.

    Arch variants that collapse to the same canonical name (rv_zba / rv64_zba
    -> Zba) are counted once.  A compound tag (rv_c_f -> C + F) contributes
    its instruction to both groups.
    """
    groups: dict[str, list[str]] = {}
    for mnemonic, entry in instr_dict.items():
        for ext in normalize_tags(entry.get("extension", [])):
            groups.setdefault(ext, []).append(mnemonic)
    return dict(sorted({k: sorted(v) for k, v in groups.items()}.items()))


def find_multi_extension_instructions(
    instr_dict: dict[str, InstrEntry],
) -> list[MultiExtInstr]:
    """
    Return all instructions whose canonical extension set has more than one member.

    An instruction with tags [rv_zba, rv64_zba] has canonical set {Zba} (size 1)
    and is excluded — those are arch variants of the same extension, not two
    distinct extensions.  Only instructions that genuinely span multiple distinct
    extensions (e.g., andn in Zbb, Zbkb, Zk, Zkn, Zks) qualify.
    """
    result = []
    for mnemonic, entry in instr_dict.items():
        raw_tags = entry.get("extension", [])
        canonical = normalize_tags(raw_tags)
        if len(canonical) > 1:
            result.append(MultiExtInstr(
                mnemonic=mnemonic,
                raw_tags=raw_tags,
                canonical_extensions=canonical,
            ))
    return sorted(result, key=lambda x: x.mnemonic)


def build_summary(instr_dict: dict[str, InstrEntry]) -> SummaryData:
    return SummaryData(
        raw_tag_groups=group_by_raw_tag(instr_dict),
        canonical_groups=group_by_canonical_extension(instr_dict),
        multi_ext=find_multi_extension_instructions(instr_dict),
        total_instructions=len(instr_dict),
    )


def print_summary_table(summary: SummaryData) -> None:
    """
    Print the extension summary table using raw tags (matching the spec format),
    followed by a note showing the canonical count after arch-variant merging.
    """
    raw = summary.raw_tag_groups
    canonical = summary.canonical_groups

    table = Table(
        title="Extension Summary",
        box=box.DOUBLE_EDGE,
        show_footer=True,
        header_style="bold cyan",
    )
    table.add_column("Extension Tag", style="bold", footer="TOTAL")
    table.add_column(
        "Instructions",
        justify="right",
        footer=str(summary.total_instructions),
    )
    table.add_column("Example Mnemonic", style="dim")

    for tag, mnemonics in raw.items():
        table.add_row(tag, str(len(mnemonics)), mnemonics[0].upper())

    console.print(table)
    console.print(
        f"  [dim]{len(raw)} raw extension tags  →  "
        f"{len(canonical)} canonical extensions "
        f"(after merging arch variants: rv_zba + rv64_zba → Zba)[/dim]\n"
    )


def print_multi_extension_list(multi_ext: list[MultiExtInstr]) -> None:
    table = Table(
        title=f"Instructions in Multiple Extensions ({len(multi_ext)} total)",
        box=box.SIMPLE_HEAD,
        header_style="bold cyan",
    )
    table.add_column("Mnemonic", style="bold")
    table.add_column("Canonical Extensions")

    for instr in multi_ext:
        exts = ", ".join(sorted(instr.canonical_extensions))
        table.add_row(instr.mnemonic.upper(), exts)

    console.print(table)
