# RISC-V Instruction Set Explorer

A Python tool that parses the RISC-V extension landscape, cross-references it against the
official ISA manual, and visualises which extensions share instructions.

Built for the LFX Mentorship coding challenge: *Mapping the RISC-V Extensions Landscape*.

---

## Quick Start

```bash
# Clone this repo
git clone <your-repo-url>
cd riscv-isa-explorer

# Install dependencies
pip install -r requirements.txt

# Run all three tiers
python main.py
```

The first run clones the ISA manual (~15 s, depth=1).  Subsequent runs use a cached copy under
`~/.cache/riscv-explorer/` and are near-instant.

---

## Usage

```
python main.py                    # run all tiers (default)
python main.py --tier 1           # Tier 1 only: instruction parsing
python main.py --tier 2           # Tier 2 only: ISA manual cross-reference
python main.py --tier 3           # Tier 3 only: extension relationship graph
python main.py --no-cache         # re-fetch everything, ignore local cache
python main.py --no-png           # skip PNG export
python main.py --graph-output out.png   # custom PNG output path
```

---

## What Each Tier Does

### Tier 1 — Instruction Set Parsing

Fetches [`instr_dict.json`](https://github.com/rpsene/riscv-extensions-landscape) and:
- Groups 1188 instructions by canonical extension name
- Prints a summary table: extension | instruction count | example mnemonic
- Lists all instructions that span more than one extension

### Tier 2 — Cross-Reference with the ISA Manual

Clones the [riscv-isa-manual](https://github.com/riscv/riscv-isa-manual) repository and:
- Scans all AsciiDoc source files for extension name references using four regex patterns
- Maps the 114 raw extension tags from the JSON to ~60 canonical names
- Reports: matched, JSON-only, and manual-only extensions with counts

### Tier 3 — Extension Relationship Graph

- Builds an undirected graph where an edge connects two extensions that share at least one instruction
- Prints a terminal summary showing clusters and the top shared instruction pairs
- Exports a PNG with community-coloured nodes, sized by instruction count

---

## Sample Output

```
━━━━━━━━━━━━━━━━━━━━━━━━ Tier 1 — Instruction Set Parsing ━━━━━━━━━━━━━━━━━━━━━━━━

╔═══════════════════════════════════════════════════════╗
║                   Extension Summary                   ║
╠══════════════╤══════════════╤═══════════════════════  ║
║ Extension    │ Instructions │ Example Mnemonic        ║
╠══════════════╪══════════════╪═══════════════════════  ║
║ A            │           11 │ AMOADD_D                ║
║ C            │           46 │ C_ADD                   ║
║ D            │           26 │ FADD_D                  ║
║ ...          │          ... │ ...                     ║
╠══════════════╪══════════════╪═══════════════════════  ║
║ TOTAL        │         1188 │                         ║
╚══════════════╧══════════════╧═══════════════════════  ╝

━━━━━━━━━━━━━━━ Tier 2 — Cross-Reference with ISA Manual ━━━━━━━━━━━━━━━━━━━━━━━━

╔══════════════════════════════════════════════════════╗
║              Cross-Reference Report                  ║
╠══════════════╤═══════╤═════════════════════════════  ║
║ Category     │ Count │ Extensions                    ║
╠══════════════╪═══════╪═════════════════════════════  ║
║ Matched      │    51 │ A, C, D, F, H, I, M, Q, Zba  ║
║ JSON only    │     9 │ Sdext, Smrnmi, Ssctr, ...     ║
║ Manual only  │    14 │ Zawrs, Zihintpause, ...       ║
╚══════════════╧═══════╧═════════════════════════════  ╝

  51 matched, 9 in JSON only, 14 in manual only

━━━━━━━━━━━━━━━━━━━━━ Tier 3 — Extension Relationship Graph ━━━━━━━━━━━━━━━━━━━━━━

  60 extensions · 143 shared-instruction edges · 4 connected component(s)

  Cluster 1 — Cryptographic (28 extensions)
    Zbkb, Zbkc, Zbkx, Zk, Zkn, Zknd, Zkne, Zknh, Zkr, Zks, ...
  ...
```

---

## Running Tests

```bash
pytest tests/ -v
```

The test suite covers normalization edge cases, grouping logic, and the adoc scanner.  No network
access is needed — all tests run against local fixtures and temporary files.

---

## Design Decisions

### Why normalization is the hard part

The JSON uses raw tags like `rv_zba`, `rv64_zba`, `rv32_zknd`, and `rv_c_f`.  The manual uses
clean names like `Zba`, `Zknd`, `C`, `F`.  Most of the mapping is mechanical (strip the arch
prefix, capitalize), but two cases break the pattern:

**Compound tags**: `rv_c_f` looks identical to `rv_smrnmi` after stripping the prefix — one
underscore, two parts.  But `c_f` means "instructions at the intersection of C and F" (two
extensions), while `smrnmi` is a single extension name that starts with the `sm` privilege prefix.
The rule: if the body starts with a known two-letter platform prefix (`sm`, `ss`, `sv`, `sh`,
`sd`), treat the whole body as one name.  Otherwise split on `_`.

**Override cases**: `rv_svinval_h` would be treated as a single name by the platform-prefix rule
(it starts with `sv`), but it actually means the Svinval extension plus the Hypervisor (`H`)
extension.  This gets an explicit override entry rather than a fragile heuristic.

### Why a shallow clone instead of the GitHub API

Scanning 80+ `.adoc` files one at a time over the GitHub API would hit rate limits fast (60
unauthenticated requests/hour).  A `git clone --depth 1` grabs everything in one shot and takes
about 15 seconds.  The clone is cached at `~/.cache/riscv-explorer/isa-manual/` so subsequent
runs skip it entirely.

### Why the graph shows clusters and not raw adjacency

With ~60 extension nodes and 140+ edges, printing an adjacency list is just noise.  Showing
connected components tells you something useful: the cryptographic extensions form a dense cluster
because many instructions (e.g., `andn`, `rol`, `clmul`) were deliberately included in multiple
Zk* sub-extensions to let implementors pick the right subset without code duplication.

### Extension count: 114 raw tags vs ~60 canonical names

The same extension shows up under multiple raw tags because `instr_dict.json` tracks
architecture-specific variants separately (`rv_zba` for the baseline definition, `rv64_zba` for
the 64-bit encoding).  After normalization these collapse to one canonical name.  The canonical
count (~60) is what matters for cross-referencing against the manual.

---

## Assumptions

- The `instr_dict.json` schema is stable: top-level keys are mnemonics, each entry has an
  `extension` field that is a list of strings.
- Extension name matching between JSON and manual is case-insensitive.
- "Manual-only" extensions are names found in `.adoc` files that don't correspond to any JSON
  extension — these include extensions documented in the manual but not yet in the instruction
  dictionary (e.g., `Zihintpause`, `Zawrs`).
- The graph connects extensions at the *canonical* level.  Two raw tags that normalize to the
  same name (`rv_zba`, `rv64_zba`) are treated as one node.
