"""
Tier 1 — Instruction Set Parsing.

Fetches instr_dict.json, groups instructions by canonical extension name,
and identifies instructions that belong to more than one extension.
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

from .normalize import normalize_tag, normalize_tags

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
    # canonical extension name -> sorted list of mnemonics
    groups: dict[str, list[str]] = field(default_factory=dict)
    multi_ext: list[MultiExtInstr] = field(default_factory=list)
    total_instructions: int = 0
    total_canonical_extensions: int = 0
    total_raw_tags: int = 0


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

    console.print(
        f"[green]✓[/green] Fetched {len(data)} instructions"
    )
    return data


def group_by_canonical_extension(
    instr_dict: dict[str, InstrEntry],
) -> dict[str, list[str]]:
    """
    Build a mapping from canonical extension name to sorted list of mnemonics.

    An instruction tagged with a compound extension (e.g., rv_c_f -> C + F)
    appears in both groups.  Arch variants that collapse to the same canonical
    name (rv_zba / rv64_zba -> Zba) are counted once.
    """
    groups: dict[str, list[str]] = {}
    for mnemonic, entry in instr_dict.items():
        canonical = normalize_tags(entry.get("extension", []))
        for ext in canonical:
            groups.setdefault(ext, []).append(mnemonic)

    # Sort mnemonics within each group, then sort the dict by extension name.
    return dict(sorted({k: sorted(v) for k, v in groups.items()}.items()))


def find_multi_extension_instructions(
    instr_dict: dict[str, InstrEntry],
) -> list[MultiExtInstr]:
    """
    Return all instructions whose canonical extension set has more than one member.

    Note the distinction from "multiple raw tags": an instruction with tags
    [rv_zba, rv64_zba] has canonical set {Zba} (size 1) and is excluded.
    Only instructions that genuinely span multiple distinct extensions qualify.
    """
    result = []
    for mnemonic, entry in instr_dict.items():
        raw_tags = entry.get("extension", [])
        canonical = normalize_tags(raw_tags)
        if len(canonical) > 1:
            result.append(
                MultiExtInstr(
                    mnemonic=mnemonic,
                    raw_tags=raw_tags,
                    canonical_extensions=canonical,
                )
            )
    return sorted(result, key=lambda x: x.mnemonic)


def build_summary(instr_dict: dict[str, InstrEntry]) -> SummaryData:
    groups = group_by_canonical_extension(instr_dict)
    multi_ext = find_multi_extension_instructions(instr_dict)
    raw_tags: set[str] = set()
    for entry in instr_dict.values():
        raw_tags.update(entry.get("extension", []))
    return SummaryData(
        groups=groups,
        multi_ext=multi_ext,
        total_instructions=len(instr_dict),
        total_canonical_extensions=len(groups),
        total_raw_tags=len(raw_tags),
    )


def print_summary_table(summary: SummaryData) -> None:
    table = Table(
        title="Extension Summary",
        box=box.DOUBLE_EDGE,
        show_footer=True,
        header_style="bold cyan",
    )
    table.add_column("Extension", style="bold", footer="TOTAL")
    table.add_column(
        "Instructions",
        justify="right",
        footer=str(summary.total_instructions),
    )
    table.add_column("Example Mnemonic", style="dim")

    for ext, mnemonics in summary.groups.items():
        table.add_row(ext, str(len(mnemonics)), mnemonics[0].upper())

    console.print(table)
    console.print(
        f"  [dim]{summary.total_canonical_extensions} canonical extensions "
        f"(from {summary.total_raw_tags} raw tags after normalization)[/dim]\n"
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
