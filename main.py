"""
RISC-V Instruction Set Explorer
--------------------------------
Runs all three challenge tiers in sequence.  Use --tier to run a specific one.

Usage
-----
    python main.py                 # all tiers
    python main.py --tier 1        # Tier 1 only (instruction parsing)
    python main.py --tier 2        # Tier 2 only (ISA manual cross-reference)
    python main.py --tier 3        # Tier 3 only (extension relationship graph)
    python main.py --no-cache      # re-fetch everything even if cached
    python main.py --no-png        # skip PNG export in Tier 3
"""

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.rule import Rule

from riscv_explorer.parser import (
    INSTR_DICT_URL,
    fetch_instr_dict,
    build_summary,
    print_summary_table,
    print_multi_extension_list,
)
from riscv_explorer.cross_ref import (
    clone_isa_manual,
    scan_isa_manual,
    build_manual_extension_set,
    cross_reference,
    print_cross_ref_report,
)
from riscv_explorer.graph import (
    build_extension_graph,
    print_graph_summary,
    export_graph_png,
)

CACHE_DIR = Path.home() / ".cache" / "riscv-explorer"
console = Console()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="RISC-V Instruction Set Explorer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--tier",
        choices=["1", "2", "3", "all"],
        default="all",
        help="Which tier to run (default: all)",
    )
    p.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore cached data and re-fetch everything",
    )
    p.add_argument(
        "--no-png",
        action="store_true",
        help="Skip PNG generation in Tier 3",
    )
    p.add_argument(
        "--graph-output",
        default="extension_graph.png",
        metavar="PATH",
        help="Output path for the extension graph PNG (default: extension_graph.png)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    run_tier = args.tier

    cache_path = None if args.no_cache else CACHE_DIR / "instr_dict.json"

    instr_dict = None
    summary = None

    # ── Tier 1 ───────────────────────────────────────────────────────────────
    if run_tier in ("1", "all"):
        console.print(Rule("[bold cyan]Tier 1 — Instruction Set Parsing[/bold cyan]"))
        instr_dict = fetch_instr_dict(url=INSTR_DICT_URL, cache_path=cache_path)
        summary = build_summary(instr_dict)
        print_summary_table(summary)
        print_multi_extension_list(summary.multi_ext)

    # ── Tier 2 ───────────────────────────────────────────────────────────────
    if run_tier in ("2", "all"):
        console.print(Rule("[bold cyan]Tier 2 — Cross-Reference with ISA Manual[/bold cyan]"))

        # If we skipped Tier 1, still need the summary for cross-referencing
        if instr_dict is None:
            instr_dict = fetch_instr_dict(url=INSTR_DICT_URL, cache_path=cache_path)
        if summary is None:
            summary = build_summary(instr_dict)

        manual_cache = None if args.no_cache else CACHE_DIR / "isa-manual"
        repo_root = clone_isa_manual(cache_dir=manual_cache)
        scan_results = scan_isa_manual(repo_root)
        manual_exts = build_manual_extension_set(scan_results)
        report = cross_reference(summary, manual_exts)
        print_cross_ref_report(report)

    # ── Tier 3 ───────────────────────────────────────────────────────────────
    if run_tier in ("3", "all"):
        console.print(Rule("[bold cyan]Tier 3 — Extension Relationship Graph[/bold cyan]"))

        if instr_dict is None:
            instr_dict = fetch_instr_dict(url=INSTR_DICT_URL, cache_path=cache_path)

        ext_graph = build_extension_graph(instr_dict)
        print_graph_summary(ext_graph)

        if not args.no_png:
            export_graph_png(ext_graph, output_path=args.graph_output)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]Error:[/red] {e}")
        sys.exit(1)
