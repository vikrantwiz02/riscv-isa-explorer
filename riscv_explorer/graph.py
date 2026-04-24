"""
Tier 3 — Extension Relationship Graph.

Two extensions are connected when they share at least one instruction.
With 76 canonical extensions and 122 multi-extension instructions, the
resulting graph is dense in the cryptographic cluster and sparse elsewhere.

Terminal output shows connected components (clusters) rather than a raw
adjacency list — 76 nodes × 48 edges as text is unreadable noise.
The PNG export gives the full picture with community colouring.
"""

from __future__ import annotations

import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich import box

from .normalize import normalize_tags
from .parser import InstrEntry

console = Console()


@dataclass
class ExtensionGraph:
    # networkx.Graph — stored as Any to keep the import optional at module level
    graph: object
    # (ext_a, ext_b) sorted tuple -> list of shared mnemonics
    shared_instructions: dict[tuple[str, str], list[str]] = field(
        default_factory=dict
    )
    # extension -> instruction count (all instructions, not just shared)
    instruction_counts: dict[str, int] = field(default_factory=dict)


def build_extension_graph(
    instr_dict: dict[str, InstrEntry],
    instruction_counts: dict[str, int] | None = None,
) -> ExtensionGraph:
    """
    Build an undirected graph where nodes are canonical extension names and
    edges connect extensions that share at least one instruction.

    Edge weight = number of shared instructions.
    """
    try:
        import networkx as nx
    except ImportError:
        raise ImportError("networkx is required for graph features: pip install networkx")

    # Collect shared instructions per extension pair
    shared: dict[tuple[str, str], list[str]] = defaultdict(list)
    for mnemonic, entry in instr_dict.items():
        canonical = normalize_tags(entry.get("extension", []))
        if len(canonical) > 1:
            for ext_a, ext_b in combinations(sorted(canonical), 2):
                shared[(ext_a, ext_b)].append(mnemonic)

    G = nx.Graph()

    # Add all extensions as nodes (including isolated ones)
    all_exts: set[str] = set()
    for entry in instr_dict.values():
        all_exts.update(normalize_tags(entry.get("extension", [])))
    G.add_nodes_from(sorted(all_exts))

    # Add edges with weight
    for (ext_a, ext_b), mnemonics in shared.items():
        G.add_edge(ext_a, ext_b, weight=len(mnemonics), mnemonics=mnemonics)

    counts = instruction_counts or {}
    if not counts:
        from .parser import group_by_canonical_extension
        groups = group_by_canonical_extension(instr_dict)
        counts = {ext: len(mnemonics) for ext, mnemonics in groups.items()}

    return ExtensionGraph(
        graph=G,
        shared_instructions=dict(shared),
        instruction_counts=counts,
    )


def _detect_communities(G) -> dict[str, int]:
    """
    Assign each node to a community ID.  Tries greedy modularity first
    (requires a connected subgraph), falls back to connected components.
    """
    try:
        import networkx as nx
        from networkx.algorithms.community import greedy_modularity_communities

        # greedy_modularity_communities works on the full graph including
        # isolated nodes since networkx 3.x — but wrap anyway.
        communities = greedy_modularity_communities(G)
        return {
            node: idx
            for idx, community in enumerate(communities)
            for node in community
        }
    except Exception:
        import networkx as nx
        mapping = {}
        for idx, component in enumerate(nx.connected_components(G)):
            for node in component:
                mapping[node] = idx
        return mapping


def print_graph_summary(ext_graph: ExtensionGraph) -> None:
    try:
        import networkx as nx
    except ImportError:
        console.print("[red]networkx not installed — skipping graph summary[/red]")
        return

    G = ext_graph.graph
    community_map = _detect_communities(G)

    # Group nodes by community
    communities: dict[int, list[str]] = defaultdict(list)
    for node, cid in community_map.items():
        communities[cid].append(node)

    # Separate isolated nodes from proper clusters
    isolated = [
        node for node in G.nodes() if G.degree(node) == 0
    ]
    clusters = {
        cid: sorted(members)
        for cid, members in sorted(
            communities.items(),
            key=lambda x: -len(x[1]),
        )
        if any(G.degree(n) > 0 for n in members)
    }

    n_components = nx.number_connected_components(G)
    console.print(
        f"\n[bold cyan]Extension Relationship Graph[/bold cyan]\n"
        f"  {G.number_of_nodes()} extensions  ·  "
        f"{G.number_of_edges()} shared-instruction edges  ·  "
        f"{n_components} connected component(s)\n"
    )

    for idx, (cid, members) in enumerate(clusters.items(), 1):
        # Guess a label from the dominant naming pattern
        label = _cluster_label(members)
        console.print(
            f"  [bold]Cluster {idx}[/bold] — {label} "
            f"[dim]({len(members)} extensions)[/dim]"
        )
        # Wrap members at ~80 chars
        line = "    "
        for m in members:
            if len(line) + len(m) + 2 > 82:
                console.print(line.rstrip(", "))
                line = "    "
            line += m + ", "
        console.print(line.rstrip(", "))
        console.print()

    if isolated:
        console.print(
            f"  [bold]Isolated[/bold] [dim]({len(isolated)} extensions — "
            f"no shared instructions with any other extension)[/dim]"
        )
        console.print("    " + ", ".join(sorted(isolated)) + "\n")

    # Top 10 most-shared pairs
    top_pairs = sorted(
        ext_graph.shared_instructions.items(),
        key=lambda x: -len(x[1]),
    )[:10]

    if top_pairs:
        table = Table(
            title="Top Shared Instruction Pairs",
            box=box.SIMPLE_HEAD,
            header_style="bold cyan",
        )
        table.add_column("Extension A", style="bold")
        table.add_column("")
        table.add_column("Extension B", style="bold")
        table.add_column("Shared", justify="right")
        table.add_column("Sample", style="dim")

        for (ext_a, ext_b), mnemonics in top_pairs:
            sample = ", ".join(m.upper() for m in mnemonics[:3])
            if len(mnemonics) > 3:
                sample += f", … (+{len(mnemonics) - 3})"
            table.add_row(ext_a, "↔", ext_b, str(len(mnemonics)), sample)

        console.print(table)


def _cluster_label(members: list[str]) -> str:
    """Heuristic label based on the naming pattern of cluster members."""
    names = [m.lower() for m in members]
    if sum(1 for n in names if n.startswith("zk") or n.startswith("zbk")) > 3:
        return "Cryptographic"
    if sum(1 for n in names if n.startswith("zv")) > 3:
        return "Vector Crypto"
    if sum(1 for n in names if n in {"i", "m", "a", "f", "d", "q", "c", "h", "v"}
                               or n.startswith("z")) > 4:
        return "Base + Extensions"
    if sum(1 for n in names if n.startswith("s")) > 2:
        return "Supervisor/Platform"
    return "Mixed"


def export_graph_png(
    ext_graph: ExtensionGraph,
    output_path: str = "extension_graph.png",
) -> None:
    """
    Export the graph as a PNG.

    Nodes are coloured by community, sized by instruction count.
    Layout uses spring_layout with a fixed seed for reproducibility.
    """
    try:
        import networkx as nx
        import matplotlib
        matplotlib.use("Agg")  # non-interactive backend
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
    except ImportError as e:
        console.print(f"[yellow]Skipping PNG export: {e}[/yellow]")
        return

    G = ext_graph.graph
    community_map = _detect_communities(G)
    n_communities = max(community_map.values()) + 1

    # Layout
    pos = nx.spring_layout(G, seed=42, k=2.5)

    # Node colours from tab20 palette
    # Use matplotlib.colormaps (deprecated cm.get_cmap was removed in 3.11)
    cmap = matplotlib.colormaps.get_cmap("tab20").resampled(n_communities)
    node_colors = [cmap(community_map.get(n, 0)) for n in G.nodes()]

    # Node size proportional to instruction count (with a minimum)
    node_sizes = [
        300 + ext_graph.instruction_counts.get(n, 0) * 12
        for n in G.nodes()
    ]

    # Edge thickness proportional to shared instruction count
    edge_weights = [G[u][v].get("weight", 1) for u, v in G.edges()]
    max_weight = max(edge_weights, default=1)
    edge_widths = [0.5 + 2.5 * (w / max_weight) for w in edge_weights]

    fig, ax = plt.subplots(figsize=(16, 12))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#0d1117")

    nx.draw_networkx_edges(
        G, pos,
        width=edge_widths,
        alpha=0.35,
        edge_color="#8b949e",
        ax=ax,
    )
    nx.draw_networkx_nodes(
        G, pos,
        node_color=node_colors,
        node_size=node_sizes,
        alpha=0.9,
        ax=ax,
    )
    nx.draw_networkx_labels(
        G, pos,
        font_size=7,
        font_color="#e6edf3",
        font_weight="bold",
        ax=ax,
    )

    ax.set_title(
        "RISC-V Extension Relationship Graph\n"
        "(edges connect extensions that share ≥1 instruction)",
        color="#e6edf3",
        fontsize=13,
        pad=16,
    )
    ax.axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()

    console.print(f"[green]✓[/green] Graph saved to [bold]{output_path}[/bold]")
