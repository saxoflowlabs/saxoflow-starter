# SaxoFlow Interactive Tutoring Platform — Implementation Plan
### Foundation → ETH Pack Demo → Scalable Multi-Agent Learning Platform

**Status**: Planning  
**Author**: SaxoFlow Labs  
**Date**: March 2026  
**Scope**: New `saxoflow/teach/` subsystem + `TutorAgent` + ETH Zurich IC Design pack  

---

## Table of Contents

1. [Vision & Principles](#1-vision--principles)
2. [What Exists Today (Baseline)](#2-what-exists-today-baseline)
3. [What Must Be Built](#3-what-must-be-built)
4. [Complete New File Map](#4-complete-new-file-map)
5. [Phase 0 — Data Contracts (Day 1 Morning)](#5-phase-0--data-contracts-day-1-morning)
6. [Phase 1 — Document Ingestion Layer (Day 1 Morning)](#6-phase-1--document-ingestion-layer-day-1-morning)
7. [Phase 2 — Command Registry (Day 1 Afternoon)](#7-phase-2--command-registry-day-1-afternoon)
8. [Phase 3 — TutorAgent (Day 1 Afternoon)](#8-phase-3--tutoragent-day-1-afternoon)
9. [Phase 4 — Session State & Context Wiring (Day 1 Evening)](#9-phase-4--session-state--context-wiring-day-1-evening)
10. [Phase 5 — Step Runner & Checks (Day 2 Morning)](#10-phase-5--step-runner--checks-day-2-morning)
11. [Phase 6 — CLI Commands (Day 2 Morning)](#11-phase-6--cli-commands-day-2-morning)
12. [Phase 7 — Agent Invocation from Tutor (Day 2 Afternoon)](#12-phase-7--agent-invocation-from-tutor-day-2-afternoon)
13. [Phase 8 — ETH Zurich Pack (Day 2 Afternoon)](#13-phase-8--eth-zurich-pack-day-2-afternoon)
14. [Phase 9 — TUI Routing Integration (Day 2 Evening)](#14-phase-9--tui-routing-integration-day-2-evening)
15. [Phase 10 — Scaling Path (Post-Demo)](#15-phase-10--scaling-path-post-demo)
16. [Files Modified in Existing Codebase](#16-files-modified-in-existing-codebase)
17. [New Dependencies](#17-new-dependencies)
18. [Non-Negotiable Architecture Rules](#18-non-negotiable-architecture-rules)
19. [SMACD Paper Revision Angle](#19-smacd-paper-revision-angle)

---

## 1. Vision & Principles

SaxoFlow becomes an **interactive tutoring platform** where:

- A university uploads a PDF tutorial (or set of PDFs/Markdown files)
- SaxoFlow indexes the documents and an instructor authors a `pack.yaml` with step definitions
- Students run `saxoflow teach start <pack>` and receive step-by-step AI-guided instruction inside the existing TUI
- The tutor is grounded in the documents at every turn — it never hallucinates steps or commands
- Where SaxoFlow wrappers exist (`saxoflow sim`, `saxoflow wave`), the tutor presents them; where they do not exist yet (synthesis, PnR), it presents native tool commands from the tutorial
- The tutor can invoke any registered SaxoFlow agent (`rtlgen`, `tbgen`, `rtlreview`, future agents) when a step requires design generation or review — bridging tutorial instruction with AI-assisted design

### The four non-negotiable guarantees

| # | Guarantee | How enforced |
|---|---|---|
| 1 | LLM always receives step + doc chunks + workspace state + conversation turns | `TeachSession` injected into every `TutorAgent` call |
| 2 | LLM never decides what command to execute | Commands come from step YAML only; `runner.py` executes; AI explains |
| 3 | Context is never lost between turns | `TeachSession` lives in `cool_cli/state.py` as a module singleton |
| 4 | Any agent is invocable from a step | `AgentDispatcher` resolves agent keys from step YAML `invoke_agent` field |

---

## 2. What Exists Today (Baseline)

### Reusable as-is (zero changes needed)

| Component | File | Role in tutoring |
|---|---|---|
| `BaseAgent` | `saxoflow_agenticai/core/base_agent.py` | `TutorAgent` inherits from this |
| `AgentManager` | `saxoflow_agenticai/core/agent_manager.py` | Register `tutor` here; invoke other agents from tutor |
| `ModelSelector` | `saxoflow_agenticai/core/model_selector.py` | `TutorAgent` uses this unmodified |
| `FeedbackCoordinator` | `saxoflow_agenticai/orchestrator/feedback_coordinator.py` | Used when tutor invokes RTLGen + RTLReview cycle |
| `AgentOrchestrator` | `saxoflow_agenticai/orchestrator/agent_orchestrator.py` | Available for `fullpipeline` steps |
| `RTLGenAgent` | `saxoflow_agenticai/agents/generators/rtl_gen.py` | Invoked for "generate RTL" steps |
| `TBGenAgent` | `saxoflow_agenticai/agents/generators/tb_gen.py` | Invoked for "generate testbench" steps |
| `RTLReviewAgent` | `saxoflow_agenticai/agents/reviewers/rtl_review.py` | Invoked for "review RTL" steps |
| `SimAgent` | `saxoflow_agenticai/agents/sim_agent.py` | Invoked for "simulate" steps |
| `cool_cli/state.py` | — | Add `teach_session` singleton here |
| `cool_cli/app.py` | — | Add 6-line routing guard for teach mode |
| `cool_cli/panels.py` | — | `tutor_panel()` added; reuses existing infrastructure |
| `saxoflow/makeflow.py` | — | `sim`, `wave`, `synth`, `formal` used as step actions |
| `saxoflow/cli.py` | — | Add `teach` sub-group; `diagnose` pattern already exists |

### What is missing

- No `TeachSession` object (context is lost between turns today)
- No document indexer or retrieval layer
- No step YAML schema or pack loader
- No command registry (no mapping from `iverilog ...` to `saxoflow sim`)
- No `TutorAgent` (current AI Buddy is a generic chatbot, not a step-bound tutor)
- No checks framework for step validation
- No agent dispatch from within a tutoring step
- No `teach` CLI group

---

## 3. What Must Be Built

### New subsystem: `saxoflow/teach/`

```
saxoflow/teach/
  __init__.py
  session.py          ← TeachSession dataclass — the spine of everything
  pack.py             ← pack.yaml + lesson YAML loader and validator
  indexer.py          ← PDF/MD → paragraph chunks → BM25 index
  retrieval.py        ← retrieve_chunks() interface (BM25 now, embeddings later)
  command_map.py      ← resolve native command → saxoflow equivalent
  checks.py           ← FileExistsCheck, LogRegexCheck, ExitCodeCheck
  runner.py           ← run step command, capture output, update session
  agent_dispatcher.py ← invoke any registered agent from within a step
  cli.py              ← Click group: teach subcommands
```

### New agent: `saxoflow_agenticai/agents/tutor_agent.py`

```
saxoflow_agenticai/agents/
  tutor_agent.py      ← TutorAgent(BaseAgent) with 5-section context bundle
```

### New prompt: `saxoflow_agenticai/prompts/`

```
saxoflow_agenticai/prompts/
  tutor_prompt.txt         ← base tutor prompt template (Jinja2)
  tutor_agent_result.txt   ← prompt for post-agent-invocation explanation
```

### New config: `saxoflow/tools/`

```
saxoflow/tools/
  registry.yaml       ← native command → saxoflow wrapper mapping
```

### New packs directory

```
packs/
  ethz_ic_design/
    pack.yaml
    docs/
      ethz_ic_tutorial.pdf   ← student provides; not committed to repo
    lessons/
      01_setup.yaml
      02_rtl_design.yaml
      03_simulation.yaml
      04_waveform.yaml
      05_synthesis.yaml
      06_formal_verification.yaml
      07_fpga_pnr.yaml
      08_asic_backend.yaml
```

---

## 4. Complete New File Map

```
saxoflow-starter/
│
├── saxoflow/
│   ├── teach/                         ← NEW SUBSYSTEM
│   │   ├── __init__.py
│   │   ├── session.py                 ← Step 5.1
│   │   ├── pack.py                    ← Step 6.1
│   │   ├── indexer.py                 ← Step 6.2
│   │   ├── retrieval.py               ← Step 6.3
│   │   ├── command_map.py             ← Step 7.1
│   │   ├── checks.py                  ← Step 10.1
│   │   ├── runner.py                  ← Step 10.2
│   │   ├── agent_dispatcher.py        ← Step 12.1
│   │   └── cli.py                     ← Step 11.1
│   └── tools/
│       ├── definitions.py             (unchanged)
│       └── registry.yaml              ← Step 7.2 (NEW)
│
├── saxoflow_agenticai/
│   ├── agents/
│   │   └── tutor_agent.py             ← Step 8.1
│   └── prompts/
│       ├── tutor_prompt.txt           ← Step 8.2
│       └── tutor_agent_result.txt     ← Step 12.2
│
├── cool_cli/
│   ├── state.py                       ← MODIFIED: add teach_session (Step 9.1)
│   ├── app.py                         ← MODIFIED: teach routing guard (Step 14.1)
│   └── panels.py                      ← MODIFIED: add tutor_panel() (Step 14.2)
│
└── packs/
    └── ethz_ic_design/                ← Step 13
        ├── pack.yaml
        ├── docs/
        │   └── .gitkeep
        └── lessons/
            ├── 01_setup.yaml
            ├── 02_rtl_design.yaml
            ├── 03_simulation.yaml
            ├── 04_waveform.yaml
            ├── 05_synthesis.yaml
            ├── 06_formal_verification.yaml
            ├── 07_fpga_pnr.yaml
            └── 08_asic_backend.yaml
```

---

## 5. Phase 0 — Data Contracts (Day 1 Morning)

### Step 5.1 — Create `saxoflow/teach/session.py`

This is the first file to write. Everything else depends on it.

```python
# saxoflow/teach/session.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class CheckDef:
    kind: str            # "file_exists" | "log_regex" | "exit_code"
    pattern: str = ""    # regex or file path or expected exit code string
    file: str = ""       # for log_regex: which log file to search


@dataclass
class CommandDef:
    native: str                          # command as written in the tutorial
    preferred: Optional[str] = None      # saxoflow equivalent if available
    use_preferred_if_available: bool = True


@dataclass
class AgentInvocationDef:
    agent_key: str          # e.g. "rtlgen", "tbgen", "rtlreview", "fullpipeline"
    args: Dict[str, str] = field(default_factory=dict)  # e.g. {spec: "source/specification/mymod.md"}
    description: str = ""   # shown to student: "Generate RTL for your module"


@dataclass
class StepDef:
    id: str
    title: str
    goal: str
    read: List[Dict[str, Any]]           # [{doc, pages}]
    commands: List[CommandDef] = field(default_factory=list)
    agent_invocations: List[AgentInvocationDef] = field(default_factory=list)
    success: List[CheckDef] = field(default_factory=list)
    hints: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class PackDef:
    id: str
    name: str
    version: str
    authors: List[str]
    description: str
    steps: List[StepDef]
    docs_dir: Path
    pack_path: Path


@dataclass
class TeachSession:
    """
    The spine of the entire tutoring system.
    Lives in cool_cli/state.py as a module singleton.
    Injected into every TutorAgent call without exception.
    """
    pack: PackDef
    current_step_index: int = 0

    # Conversation memory (last N turns used in LLM context)
    conversation_turns: List[Dict[str, str]] = field(default_factory=list)
    MAX_HISTORY_TURNS: int = 6

    # Workspace state (updated after every step command run)
    last_run_log: str = ""
    last_run_exit_code: int = -1
    last_run_command: str = ""
    workspace_snapshot: Dict[str, bool] = field(default_factory=dict)

    # Progress (persisted to .saxoflow/teach/progress.json)
    checks_passed: Dict[str, bool] = field(default_factory=dict)
    agent_results: Dict[str, str] = field(default_factory=dict)   # step_id → agent output

    # Derived properties
    @property
    def current_step(self) -> StepDef:
        return self.pack.steps[self.current_step_index]

    @property
    def total_steps(self) -> int:
        return len(self.pack.steps)

    @property
    def is_complete(self) -> bool:
        return self.current_step_index >= self.total_steps

    def add_turn(self, role: str, content: str) -> None:
        self.conversation_turns.append({"role": role, "content": content})
        if len(self.conversation_turns) > self.MAX_HISTORY_TURNS * 2:
            self.conversation_turns = self.conversation_turns[-(self.MAX_HISTORY_TURNS * 2):]

    def advance(self) -> bool:
        """Move to next step. Returns False if already at last step."""
        if self.current_step_index < self.total_steps - 1:
            self.current_step_index += 1
            return True
        return False

    def mark_check_passed(self, step_id: str) -> None:
        self.checks_passed[step_id] = True

    def store_agent_result(self, step_id: str, result: str) -> None:
        self.agent_results[step_id] = result
```

**Why this must be first**: `TutorAgent`, `pack.py`, `runner.py`, `checks.py`, `agent_dispatcher.py`, and `cli.py` all import from `session.py`. If you build them in the wrong order you will refactor constantly.

---

## 6. Phase 1 — Document Ingestion Layer (Day 1 Morning)

### Step 6.1 — Create `saxoflow/teach/pack.py`

Loads and validates `pack.yaml` and all lesson YAMLs into `PackDef` / `StepDef` dataclasses.

**pack.yaml schema** (top-level):

```yaml
id: ethz_ic_design
name: "ETH Zurich IC Design Tutorial"
version: "1.0"
authors: ["ETH Zurich"]
description: "End-to-end IC design from RTL to GDS"
docs:
  - filename: ethz_ic_tutorial.pdf
    type: pdf
lessons:
  - 01_setup.yaml
  - 02_rtl_design.yaml
  - 03_simulation.yaml
  - 04_waveform.yaml
  - 05_synthesis.yaml
  - 06_formal_verification.yaml
  - 07_fpga_pnr.yaml
  - 08_asic_backend.yaml
```

**Lesson YAML schema** (per step):

```yaml
id: sim_run
title: "Run RTL Simulation with Icarus Verilog"
goal: >
  Compile your RTL and testbench with Icarus Verilog and execute
  the simulation to observe signal behavior.
read:
  - doc: ethz_ic_tutorial.pdf
    pages: "20-24"
    section: "3.2 Simulation with Icarus"

commands:
  - native: "iverilog -g2012 -o sim.out source/tb/verilog/tb.v source/rtl/verilog/dut.v"
    preferred: "saxoflow sim"
    use_preferred_if_available: true
  - native: "vvp sim.out"
    preferred: "saxoflow sim"
    use_preferred_if_available: true

agent_invocations: []   # no agent needed for this step

success:
  - kind: file_exists
    file: "simulation/icarus/tb.vcd"
  - kind: log_regex
    file: ".saxoflow/teach/runs/sim_run.log"
    pattern: "TEST PASSED|Simulation complete"

hints:
  - "If 'iverilog not found': run saxoflow install iverilog"
  - "If 'module not found': check your RTL file path"
  - "If VCD not generated: add \$dumpfile/\$dumpvars to your testbench"

notes: "This step assumes you completed 02_rtl_design before proceeding."
```

**Lesson YAML with agent invocation** (example: RTL generation step):

```yaml
id: rtl_generate
title: "Generate RTL from Specification Using AI"
goal: >
  Use the SaxoFlow RTL generation agent to create synthesizable Verilog
  from your design specification markdown file.
read:
  - doc: ethz_ic_tutorial.pdf
    pages: "8-12"
    section: "2.1 Writing a Design Specification"

commands: []  # no direct tool commands; agent handles this

agent_invocations:
  - agent_key: rtlgen
    description: "Generate synthesizable Verilog-2001 RTL from your spec"
    args:
      spec_file: "source/specification/"   # tutor will prompt student for the actual file
      output_dir: "source/rtl/verilog/"

success:
  - kind: file_exists
    file: "source/rtl/verilog/"   # any .v file in this directory

hints:
  - "Make sure your spec file is in source/specification/"
  - "Describe ports, functionality, and reset behaviour clearly in the spec"

notes: >
  The agent will invoke RTLGenAgent followed by RTLReviewAgent automatically.
  Up to 3 improvement iterations will run before the result is written.
```

**Implementation notes for `pack.py`**:
- Use `PyYAML` (already in `requirements.txt`) for loading
- Validate required fields; raise `ValueError` with a human-readable message on schema violations
- Return `PackDef` with all `StepDef` objects pre-loaded
- Resolve `docs_dir` as `pack_path / "docs"`

### Step 6.2 — Create `saxoflow/teach/indexer.py`

```python
# saxoflow/teach/indexer.py
"""
PDF/Markdown document indexer for the SaxoFlow tutoring system.

Build phase (one-time per pack):
  DocIndex(pack).build()  →  .saxoflow/teach/index/<pack_id>.pkl

Runtime phase:
  DocIndex(pack).retrieve(query, top_k) → list[Chunk]

Design rules:
  - BM25 now (rank-bm25, pure Python, no ML infra required)
  - The retrieve() interface is frozen; swap BM25 for embeddings later
    without changing any caller.
"""
from __future__ import annotations
import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

@dataclass
class Chunk:
    text: str
    source_doc: str
    page_num: int          # -1 if not applicable (Markdown)
    section_hint: str = "" # paragraph heading if detectable


class DocIndex:
    INDEX_DIR = Path(".saxoflow/teach/index")

    def __init__(self, pack):            # pack: PackDef
        self.pack = pack
        self._index_path = self.INDEX_DIR / f"{pack.id}.pkl"
        self._chunks: List[Chunk] = []
        self._bm25 = None

    def build(self) -> None:
        """Extract text from all pack docs and build BM25 index."""
        ...  # see implementation detail below

    def load_or_build(self) -> None:
        """Load existing index or build from scratch."""
        ...

    def retrieve(self, query: str, top_k: int = 3) -> List[Chunk]:
        """Top-k BM25 retrieval. Interface is stable across BM25/embeddings."""
        ...
```

**PDF extraction approach**:
- Use `pypdf.PdfReader` (new API in pypdf ≥ 3.x)
- Extract text page by page
- Chunk by paragraph: split on `\n\n` after stripping boilerplate headers/footers
- Target chunk size: 250–400 words; split longer paragraphs at sentence boundaries
- Store `{text, source_doc, page_num}` per chunk

**Markdown extraction approach**:
- Split on `##` heading boundaries
- Each section becomes one chunk
- Store heading text as `section_hint`

**BM25 index**:
- Tokenize each chunk: lowercase, split on `\W+`, no stopword removal (keeps tool names like `iverilog`, `yosys`)
- Use `BM25Okapi` from `rank-bm25`
- Persist index + chunk list to pickle file under `.saxoflow/teach/index/`

### Step 6.3 — Create `saxoflow/teach/retrieval.py`

```python
# saxoflow/teach/retrieval.py
"""
Single stable interface for document retrieval.
Callers always use retrieve_chunks(); the backend (BM25 / embeddings) is hidden.
"""
from __future__ import annotations
from typing import List
from .indexer import Chunk, DocIndex

def retrieve_chunks(session, query: str, top_k: int = 3) -> List[Chunk]:
    """
    Retrieve top-k document chunks relevant to query.

    Parameters
    ----------
    session : TeachSession
        Active tutoring session (provides pack reference for index lookup).
    query : str
        The student's question or the current step title + goal.
    top_k : int
        Number of chunks to return.

    Returns
    -------
    list[Chunk]
        Ranked chunks with source citation metadata.

    Notes
    -----
    The implementation below uses BM25. To upgrade to embeddings:
      1. Replace BM25Okapi with a vector store lookup in DocIndex.retrieve()
      2. This function requires zero changes.
    """
    index = DocIndex(session.pack)
    index.load_or_build()
    return index.retrieve(query, top_k=top_k)
```

---

## 7. Phase 2 — Command Registry (Day 1 Afternoon)

### Step 7.1 — Create `saxoflow/tools/registry.yaml`

This is the single source of truth for command translation. An instructor or developer maintains this file. The AI never reads or modifies it.

```yaml
# saxoflow/tools/registry.yaml
# Maps native open-source tool commands to SaxoFlow wrappers.
# status: available | planned | not_planned
# When status is "available", the tutor presents the saxoflow command as primary.
# The native command is always shown as a fallback.

commands:
  - id: iverilog_compile_run
    native_pattern: "iverilog"
    saxoflow: "saxoflow sim"
    status: available
    category: simulation
    notes: "saxoflow sim auto-resolves TB and RTL files from project layout"

  - id: vvp_run
    native_pattern: "vvp"
    saxoflow: "saxoflow sim"
    status: available
    category: simulation
    notes: "vvp execution is handled internally by saxoflow sim"

  - id: gtkwave
    native_pattern: "gtkwave"
    saxoflow: "saxoflow wave"
    status: available
    category: waveform

  - id: verilator_build
    native_pattern: "verilator"
    saxoflow: "saxoflow sim_verilator"
    status: available
    category: simulation

  - id: yosys_synth
    native_pattern: "yosys"
    saxoflow: "saxoflow synth"
    status: available
    category: synthesis

  - id: symbiyosys_formal
    native_pattern: "sby"
    saxoflow: "saxoflow formal"
    status: available
    category: formal_verification

  - id: openroad_pnr
    native_pattern: "openroad"
    saxoflow: "saxoflow pnr"
    status: planned
    category: place_and_route
    notes: "saxoflow pnr wrapper not yet implemented; use native command"

  - id: klayout_view
    native_pattern: "klayout"
    saxoflow: "saxoflow layout"
    status: planned
    category: layout

  - id: magic_drc
    native_pattern: "magic"
    saxoflow: "saxoflow drc"
    status: planned
    category: layout

  - id: nextpnr_fpga
    native_pattern: "nextpnr"
    saxoflow: "saxoflow pnr_fpga"
    status: planned
    category: fpga_pnr
```

### Step 7.2 — Create `saxoflow/teach/command_map.py`

```python
# saxoflow/teach/command_map.py
"""
Deterministic command translation layer.

The AI never decides which command to run.
This module decides: given a native tool command from the tutorial,
is there a SaxoFlow wrapper available today?

Usage:
    from saxoflow.teach.command_map import resolve_command
    result = resolve_command("iverilog -g2012 -o sim.out tb.v dut.v")
    # Returns: CommandResolution(native=..., preferred="saxoflow sim", available=True)
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import yaml

REGISTRY_PATH = Path(__file__).parent.parent / "tools" / "registry.yaml"

@dataclass
class CommandResolution:
    native: str
    preferred: Optional[str]       # None if no wrapper available
    available: bool                # True if wrapper status == "available"
    category: str
    notes: str = ""


def resolve_command(native_cmd: str) -> CommandResolution:
    """
    Given a native command string, return the saxoflow equivalent if available.
    Matching is done by checking if any registry native_pattern is a substring
    of the command's first token.
    """
    registry = _load_registry()
    first_token = native_cmd.strip().split()[0] if native_cmd.strip() else ""
    for entry in registry.get("commands", []):
        if entry["native_pattern"] in first_token or first_token in entry["native_pattern"]:
            return CommandResolution(
                native=native_cmd,
                preferred=entry.get("saxoflow"),
                available=entry.get("status") == "available",
                category=entry.get("category", ""),
                notes=entry.get("notes", ""),
            )
    return CommandResolution(native=native_cmd, preferred=None, available=False, category="")


def _load_registry() -> dict:
    with open(REGISTRY_PATH) as f:
        return yaml.safe_load(f)
```

---

## 8. Phase 3 — TutorAgent (Day 1 Afternoon)

### Step 8.1 — Create `saxoflow_agenticai/agents/tutor_agent.py`

The tutor is a `BaseAgent` subclass whose entire value is in how it constructs its context bundle. The LLM call itself is standard.

```python
# saxoflow_agenticai/agents/tutor_agent.py
"""
TutorAgent: document-grounded, step-bound interactive tutor.

Extends BaseAgent. The key difference from all other agents is the
context bundle: step + doc chunks + workspace state + conversation turns.
All five are injected deterministically into every LLM call.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, List, Optional
from ..core.base_agent import BaseAgent
from saxoflow.teach.retrieval import retrieve_chunks
from saxoflow.teach.command_map import resolve_command

if TYPE_CHECKING:
    from saxoflow.teach.session import TeachSession, Chunk


class TutorAgent(BaseAgent):
    TEMPLATE_NAME = "tutor_prompt.txt"

    def run(self, user_input: str, session: "TeachSession") -> str:
        """
        Respond to student input, grounded in step + docs + workspace state.

        Parameters
        ----------
        user_input : str
            Student's question or free-form input.
        session : TeachSession
            Active tutoring session. Provides all context required.

        Returns
        -------
        str
            Tutor response string.
        """
        context = self._build_context_bundle(user_input, session)
        prompt = self.render_prompt(context)
        response = self.query_model(prompt)
        session.add_turn("student", user_input)
        session.add_turn("tutor", response)
        return response

    # ------------------------------------------------------------------
    # Context bundle construction (the core value of this class)
    # ------------------------------------------------------------------

    def _build_context_bundle(self, user_input: str, session: "TeachSession") -> dict:
        step = session.current_step

        # Layer 1: command registry context
        command_registry_text = self._build_command_registry_text(step)

        # Layer 2: current step definition
        step_text = self._build_step_text(step, session)

        # Layer 3: relevant doc chunks (retrieval)
        query = f"{step.title} {step.goal} {user_input}"
        chunks = retrieve_chunks(session, query, top_k=3)
        doc_context = self._format_chunks(chunks)

        # Layer 4: workspace state
        workspace_text = self._build_workspace_text(session)

        # Layer 5: conversation history (last N turns)
        history_text = self._build_history_text(session)

        return {
            "command_registry": command_registry_text,
            "step_context": step_text,
            "doc_context": doc_context,
            "workspace_state": workspace_text,
            "conversation_history": history_text,
            "student_input": user_input,
            "step_index": session.current_step_index + 1,
            "total_steps": session.total_steps,
        }

    def _build_step_text(self, step, session) -> str:
        lines = [
            f"Step {session.current_step_index + 1}/{session.total_steps}: {step.title}",
            f"Goal: {step.goal}",
        ]
        if step.commands:
            lines.append("\nCommands for this step:")
            for cmd_def in step.commands:
                resolution = resolve_command(cmd_def.native)
                if resolution.available and cmd_def.use_preferred_if_available:
                    lines.append(f"  PREFERRED (SaxoFlow): {resolution.preferred}")
                    lines.append(f"  NATIVE (tutorial):    {cmd_def.native}")
                else:
                    lines.append(f"  COMMAND: {cmd_def.native}")
                    if resolution.preferred:
                        lines.append(f"  NOTE: SaxoFlow wrapper '{resolution.preferred}' is planned but not yet available.")
        if step.agent_invocations:
            lines.append("\nAI Agents available for this step:")
            for inv in step.agent_invocations:
                lines.append(f"  Agent: {inv.agent_key} — {inv.description}")
        if step.success:
            lines.append("\nThis step is complete when:")
            for chk in step.success:
                if chk.kind == "file_exists":
                    lines.append(f"  - File exists: {chk.file or chk.pattern}")
                elif chk.kind == "log_regex":
                    lines.append(f"  - Log contains: {chk.pattern}")
        if step.hints:
            lines.append("\nCommon issues:")
            for h in step.hints:
                lines.append(f"  - {h}")
        return "\n".join(lines)

    def _build_command_registry_text(self, step) -> str:
        if not step.commands:
            return "No tool commands required for this step."
        lines = ["SaxoFlow command availability:"]
        for cmd_def in step.commands:
            r = resolve_command(cmd_def.native)
            status = "AVAILABLE" if r.available else ("PLANNED" if r.preferred else "USE NATIVE")
            lines.append(f"  {cmd_def.native.split()[0]} → {r.preferred or 'no wrapper'} [{status}]")
        return "\n".join(lines)

    def _format_chunks(self, chunks) -> str:
        if not chunks:
            return "No document excerpts retrieved for this query."
        parts = []
        for i, chunk in enumerate(chunks, 1):
            citation = f"{chunk.source_doc}, p.{chunk.page_num}" if chunk.page_num >= 0 else chunk.source_doc
            parts.append(f"[Excerpt {i} — {citation}]\n{chunk.text.strip()}")
        return "\n\n---\n\n".join(parts)

    def _build_workspace_text(self, session) -> str:
        lines = [f"Last command: {session.last_run_command or 'none'}",
                 f"Last exit code: {session.last_run_exit_code}"]
        if session.last_run_log:
            tail = "\n".join(session.last_run_log.splitlines()[-20:])
            lines.append(f"Last output (tail):\n{tail}")
        if session.workspace_snapshot:
            lines.append("Expected artifacts:")
            for path, exists in session.workspace_snapshot.items():
                mark = "[OK]" if exists else "[MISSING]"
                lines.append(f"  {mark} {path}")
        return "\n".join(lines)

    def _build_history_text(self, session) -> str:
        if not session.conversation_turns:
            return ""
        turns = session.conversation_turns[-session.MAX_HISTORY_TURNS * 2:]
        return "\n".join(f"{t['role'].capitalize()}: {t['content']}" for t in turns)
```

### Step 8.2 — Create `saxoflow_agenticai/prompts/tutor_prompt.txt`

```
You are the SaxoFlow Tutor, a precise and patient digital design instructor.
You teach students IC design step by step, using only the provided document excerpts as your knowledge source.
You NEVER invent commands, tools, or concepts not present in the excerpts or step definition.

=== TOOL KNOWLEDGE ===
{{ command_registry }}

=== CURRENT STEP ({{ step_index }}/{{ total_steps }}) ===
{{ step_context }}

=== DOCUMENT EXCERPTS ===
{{ doc_context }}

=== STUDENT WORKSPACE ===
{{ workspace_state }}

=== CONVERSATION SO FAR ===
{{ conversation_history }}

=== STUDENT INPUT ===
{{ student_input }}

=== YOUR RESPONSE ===

Respond in this structure:
1. WHAT (1-2 sentences: what this step/question is about, citing the document if relevant)
2. DO (the exact command or action the student should take next — prefer SaxoFlow wrappers when [AVAILABLE])
3. WHY (brief explanation from the document excerpt, with citation: "Per [source, p.XX]: ...")
4. VERIFY (which check tells the student this worked, e.g. "Run saxoflow teach check to confirm simulation/icarus/tb.vcd was created")

If the student is asking about an agent invocation (RTL generation, testbench generation, review):
  - Explain what the agent does
  - Show the exact CLI command: saxoflow agenticai rtlgen --input <spec_file> --output <dir>
  - OR tell them to type the intent directly in the TUI (e.g., "generate rtl for my_module")

Keep responses concise. Do not provide code unless the student specifically asks.
Do not answer questions outside the scope of the current step and the provided document excerpts.
If a question is out of scope, say so and redirect to the current step.
```

### Step 8.3 — Register TutorAgent in `AgentManager`

In `saxoflow_agenticai/core/agent_manager.py`, add to `AGENT_MAP`:

```python
# In AGENT_MAP dict (existing file, one-line addition):
"tutor": ("saxoflow_agenticai.agents.tutor_agent", "TutorAgent"),
```

---

## 9. Phase 4 — Session State & Context Wiring (Day 1 Evening)

### Step 9.1 — Modify `cool_cli/state.py`

Add the `teach_session` singleton. This is a one-time four-line change:

```python
# In cool_cli/state.py — add after existing singleton declarations

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from saxoflow.teach.session import TeachSession

# Teach mode session — None when not in tutoring mode
teach_session: Optional["TeachSession"] = None
```

Add to `__all__`:
```python
"teach_session",
```

Add to `reset_state()`:
```python
global teach_session
teach_session = None
```

### Step 9.2 — Modify `cool_cli/app.py` — routing guard

In the main input routing loop, add the teach-mode guard. The existing routing is untouched; this is an early-exit branch before the AI Buddy path:

```python
# In cool_cli/app.py — inside the main loop, BEFORE the ai_buddy_interactive call

from .state import teach_session as _teach_session_ref

# After routing for built-ins, agentic commands, and shell commands:
# Check if we are in teach mode
import cool_cli.state as _state
if _state.teach_session is not None:
    from saxoflow.teach._tui_bridge import handle_teach_input
    response = handle_teach_input(user_input, _state.teach_session)
    _print_and_record(user_input, response, "tutor", panel_width)
    continue

# Existing AI Buddy path (unchanged):
result = ai_buddy_interactive(user_input, conversation_history)
```

`saxoflow/teach/_tui_bridge.py` is a thin adapter (created in Phase 9) that calls `TutorAgent` and returns a Rich-renderable.

---

## 10. Phase 5 — Step Runner & Checks (Day 2 Morning)

### Step 10.1 — Create `saxoflow/teach/checks.py`

```python
# saxoflow/teach/checks.py
"""
Deterministic step validation checks.
Each check returns (passed: bool, message: str).
"""
from __future__ import annotations
import re
from pathlib import Path
from .session import CheckDef


def run_check(check: CheckDef, project_root: Path) -> tuple[bool, str]:
    if check.kind == "file_exists":
        target = project_root / check.pattern if check.pattern else project_root / check.file
        exists = any(project_root.glob(str(check.pattern))) if "*" in str(check.pattern) else target.exists()
        return exists, f"[OK] {check.pattern}" if exists else f"[MISSING] {check.pattern}"

    elif check.kind == "log_regex":
        log_path = Path(check.file)
        if not log_path.exists():
            return False, f"[NO LOG] {check.file}"
        content = log_path.read_text(errors="replace")
        matched = bool(re.search(check.pattern, content, re.IGNORECASE))
        return matched, f"[PASS] pattern found" if matched else f"[FAIL] pattern '{check.pattern}' not found in {check.file}"

    elif check.kind == "exit_code":
        expected = int(check.pattern) if check.pattern else 0
        # Caller must set session.last_run_exit_code before calling checks
        return False, "exit_code check requires caller to provide exit code"

    return False, f"[UNKNOWN CHECK KIND] {check.kind}"


def run_all_checks(step, session, project_root: Path) -> list[tuple[bool, str]]:
    results = []
    for chk in step.success:
        passed, msg = run_check(chk, project_root)
        results.append((passed, msg))
    all_passed = all(r[0] for r in results)
    if all_passed:
        session.mark_check_passed(step.id)
    return results
```

### Step 10.2 — Create `saxoflow/teach/runner.py`

```python
# saxoflow/teach/runner.py
"""
Step command executor.

Rules:
  - Executes only commands declared in step YAML. Never executes AI-suggested commands.
  - Captures stdout+stderr into session.last_run_log.
  - Updates session state after every run.
  - Logs to .saxoflow/teach/runs/<step_id>.log for persistence.
"""
from __future__ import annotations
import subprocess
from pathlib import Path
from .session import TeachSession, CommandDef
from .command_map import resolve_command

LOG_DIR = Path(".saxoflow/teach/runs")


def run_step_command(cmd_def: CommandDef, session: TeachSession, project_root: Path) -> tuple[int, str]:
    """
    Execute the appropriate command for a step.

    Selects preferred (SaxoFlow) command if available and the step allows it.
    Falls back to native command otherwise.

    Returns (exit_code, combined_output).
    """
    resolution = resolve_command(cmd_def.native)
    if resolution.available and cmd_def.use_preferred_if_available:
        command = resolution.preferred
    else:
        command = cmd_def.native

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{session.current_step.id}.log"

    result = subprocess.run(
        command,
        shell=True,
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    combined_output = result.stdout + result.stderr

    # Update session state
    session.last_run_command = command
    session.last_run_exit_code = result.returncode
    session.last_run_log = combined_output

    # Persist to log file
    log_path.write_text(combined_output, encoding="utf-8", errors="replace")

    return result.returncode, combined_output
```

---

## 11. Phase 6 — CLI Commands (Day 2 Morning)

### Step 11.1 — Create `saxoflow/teach/cli.py`

```python
# saxoflow/teach/cli.py
"""
saxoflow teach <subcommand>

Subcommands:
  add-pack <path>    Index a teaching pack (run once per pack)
  start <pack_id>    Begin a tutoring session
  status             Show current step and progress
  next               Advance to next step (only if checks pass)
  prev               Go back to previous step
  run                Execute this step's command
  check              Run success checks for the current step
  ask "<question>"   Ask the tutor a question about the current step
  quit               End the tutoring session
"""
import click
import cool_cli.state as _state
from .pack import load_pack
from .indexer import DocIndex
from .runner import run_step_command
from .checks import run_all_checks
from saxoflow_agenticai.core.agent_manager import AgentManager
from saxoflow.teach.session import TeachSession
from pathlib import Path


@click.group()
def teach():
    """Interactive document-grounded tutoring commands."""
    pass


@teach.command("add-pack")
@click.argument("pack_path", type=click.Path(exists=True))
def add_pack(pack_path: str):
    """Index a teaching pack. Run once after adding documents."""
    pack = load_pack(Path(pack_path))
    click.echo(f"Indexing pack: {pack.name} ({len(pack.steps)} steps)...")
    idx = DocIndex(pack)
    idx.build()
    click.secho(f"[OK] Pack indexed: {pack.id}", fg="green")


@teach.command("start")
@click.argument("pack_id")
@click.option("--packs-dir", default="packs", help="Directory containing packs")
def start(pack_id: str, packs_dir: str):
    """Start a tutoring session for a pack."""
    pack_path = Path(packs_dir) / pack_id
    if not pack_path.exists():
        click.secho(f"Pack not found: {pack_path}", fg="red")
        return
    pack = load_pack(pack_path)
    idx = DocIndex(pack)
    idx.load_or_build()
    session = TeachSession(pack=pack)
    _state.teach_session = session
    click.secho(f"\nTutoring session started: {pack.name}", fg="cyan")
    click.secho(f"Step 1/{session.total_steps}: {session.current_step.title}", fg="yellow")
    click.echo(f"\nGoal: {session.current_step.goal}")
    click.echo("\nType your questions below, or use: teach run, teach check, teach next")


@teach.command("status")
def status():
    """Show current step and progress summary."""
    session = _require_session()
    if not session:
        return
    step = session.current_step
    click.secho(f"\n=== Teach Session: {session.pack.name} ===", fg="cyan")
    click.secho(f"Step {session.current_step_index + 1}/{session.total_steps}: {step.title}", fg="yellow")
    click.echo(f"Goal: {step.goal}")
    passed = session.checks_passed.get(step.id, False)
    status_str = "[PASS]" if passed else "[pending]"
    click.secho(f"Checks: {status_str}", fg="green" if passed else "yellow")


@teach.command("run")
@click.option("--project", default=".", help="Project root directory")
@click.option("--cmd-index", default=0, help="Index of command in step (default: 0)")
def run_cmd(project: str, cmd_index: int):
    """Execute this step's command."""
    session = _require_session()
    if not session:
        return
    step = session.current_step
    if not step.commands:
        click.echo("This step has no commands to run. Use 'teach ask' to get guidance.")
        return
    if cmd_index >= len(step.commands):
        click.secho(f"Command index {cmd_index} out of range.", fg="red")
        return
    cmd_def = step.commands[cmd_index]
    click.echo(f"Running: {cmd_def.native}")
    exit_code, output = run_step_command(cmd_def, session, Path(project))
    click.echo(output[-3000:])   # show last 3000 chars
    if exit_code == 0:
        click.secho("[OK] Command completed successfully.", fg="green")
    else:
        click.secho(f"[WARNING] Command exited with code {exit_code}. Run 'teach check' to verify.", fg="yellow")


@teach.command("check")
@click.option("--project", default=".", help="Project root directory")
def check(project: str):
    """Run success checks for the current step."""
    session = _require_session()
    if not session:
        return
    results = run_all_checks(session.current_step, session, Path(project))
    all_passed = True
    for passed, msg in results:
        color = "green" if passed else "red"
        click.secho(f"  {msg}", fg=color)
        if not passed:
            all_passed = False
    if all_passed:
        click.secho("\n[PASS] All checks passed. Type 'teach next' to continue.", fg="green")
    else:
        click.secho("\n[FAIL] Some checks failed. Type 'teach ask' for help.", fg="red")


@teach.command("next")
def next_step():
    """Advance to the next step."""
    session = _require_session()
    if not session:
        return
    if not session.checks_passed.get(session.current_step.id, False):
        click.secho("Current step checks not yet passed. Run 'teach check' first.", fg="yellow")
        return
    if session.advance():
        step = session.current_step
        click.secho(f"\nStep {session.current_step_index + 1}/{session.total_steps}: {step.title}", fg="cyan")
        click.echo(f"Goal: {step.goal}")
    else:
        click.secho("Congratulations — you have completed all steps!", fg="green")


@teach.command("prev")
def prev_step():
    """Go back to the previous step."""
    session = _require_session()
    if not session:
        return
    if session.current_step_index > 0:
        session.current_step_index -= 1
        step = session.current_step
        click.secho(f"\nBack to Step {session.current_step_index + 1}: {step.title}", fg="yellow")
    else:
        click.echo("Already at the first step.")


@teach.command("ask")
@click.argument("question")
def ask(question: str):
    """Ask the tutor a question about the current step (uses TutorAgent)."""
    session = _require_session()
    if not session:
        return
    agent = AgentManager.get_agent("tutor")
    response = agent.run(question, session)
    click.echo(f"\n{response}\n")


@teach.command("quit")
def quit_session():
    """End the tutoring session."""
    _state.teach_session = None
    click.secho("Tutoring session ended.", fg="cyan")


def _require_session():
    if _state.teach_session is None:
        click.secho("No active tutoring session. Run: saxoflow teach start <pack_id>", fg="red")
        return None
    return _state.teach_session
```

### Step 11.2 — Register `teach` group in `saxoflow/cli.py`

One import and one `add_command` call (same pattern as `diagnose`):

```python
# In saxoflow/cli.py — add after existing imports
from saxoflow.teach.cli import teach

# In the commands registration section — add after existing add_command calls:
cli.add_command(teach)
```

---

## 12. Phase 7 — Agent Invocation from Tutor (Day 2 Afternoon)

This is the critical bridge: a tutoring step can declare `agent_invocations` that trigger RTLGenAgent, TBGenAgent, RTLReviewAgent, fullpipeline, or any future agent. The entire existing agent infrastructure becomes accessible from within a tutoring step.

### Step 12.1 — Create `saxoflow/teach/agent_dispatcher.py`

```python
# saxoflow/teach/agent_dispatcher.py
"""
Dispatches registered agents from within a tutoring step.

Any agent registered in AgentManager.AGENT_MAP is callable from here.
This makes the full agent catalog (current and future) available to
step authors via the pack YAML.

Supported agent_key values (current):
  rtlgen, tbgen, fpropgen, report,
  rtlreview, tbreview, fpropreview,
  debug, sim, fullpipeline, tutor

Future agents (add to AGENT_MAP, automatically available here):
  timing_analysis, synth_agent, pnr_agent, etc.
"""
from __future__ import annotations
from typing import Optional
from saxoflow_agenticai.core.agent_manager import AgentManager
from saxoflow_agenticai.orchestrator.agent_orchestrator import AgentOrchestrator
from .session import TeachSession, AgentInvocationDef


def dispatch_agent(inv: AgentInvocationDef, session: TeachSession, project_root: str = ".") -> str:
    """
    Invoke the agent declared in an AgentInvocationDef.

    For generator/reviewer agents: calls agent.run() with args from the invocation.
    For fullpipeline: delegates to AgentOrchestrator.full_pipeline().

    Returns the agent's output as a string, which is also stored in session.agent_results.
    """
    agent_key = inv.agent_key
    args = inv.args or {}

    if agent_key == "fullpipeline":
        result = _run_full_pipeline(args, project_root)
    else:
        result = _run_single_agent(agent_key, args)

    session.store_agent_result(session.current_step.id, result)
    return result


def available_agents() -> list[str]:
    """Return all currently registered agent keys."""
    return AgentManager.all_agent_names()


def _run_single_agent(agent_key: str, args: dict) -> str:
    agent = AgentManager.get_agent(agent_key)
    # Dispatch based on known agent argument patterns
    if agent_key == "rtlgen":
        spec = _read_file(args.get("spec_file", ""))
        return agent.run(spec)

    elif agent_key == "tbgen":
        spec = _read_file(args.get("spec_file", ""))
        rtl = _read_file(args.get("rtl_file", ""))
        module_name = args.get("module_name", "")
        return agent.run(spec, rtl, module_name)

    elif agent_key in ("rtlreview", "tbreview", "fpropreview"):
        spec = _read_file(args.get("spec_file", ""))
        code = _read_file(args.get("code_file", ""))
        return agent.run(spec, code)

    elif agent_key == "debug":
        rtl = _read_file(args.get("rtl_file", ""))
        tb = _read_file(args.get("tb_file", ""))
        stdout = args.get("stdout", "")
        stderr = args.get("stderr", "")
        result, _ = agent.run(rtl, tb, stdout, stderr, "")
        return result

    elif agent_key == "sim":
        return str(agent.run(args.get("project_path", "."), args.get("top_module", "")))

    else:
        # Generic fallback — pass all args as kwargs if agent accepts them
        return agent.run(**args)


def _run_full_pipeline(args: dict, project_root: str) -> str:
    orchestrator = AgentOrchestrator()
    results = orchestrator.full_pipeline(
        spec_file=args.get("spec_file", "source/specification/spec.md"),
        project_path=args.get("project_path", project_root),
        max_iters=int(args.get("max_iters", 3)),
    )
    return results.get("pipeline_report", str(results))


def _read_file(path: str) -> str:
    if not path:
        return ""
    try:
        from pathlib import Path
        return Path(path).read_text()
    except Exception:
        return ""
```

### Step 12.2 — Create `saxoflow_agenticai/prompts/tutor_agent_result.txt`

Used when the tutor needs to explain an agent's output to the student:

```
The {{ agent_key }} agent has completed.

=== STEP CONTEXT ===
{{ step_context }}

=== AGENT OUTPUT ===
{{ agent_output }}

=== STUDENT CONTEXT ===
{{ workspace_state }}

Explain the agent result to the student concisely (3-5 sentences):
1. What the agent produced
2. Where the output was written
3. What the student should do next (the next step command or check)
4. Any caveats or things to verify

Do not reproduce the full agent output. Summarize and guide.
```

### Step 12.3 — Add `teach invoke-agent` CLI command

Add to `saxoflow/teach/cli.py`:

```python
@teach.command("invoke-agent")
@click.argument("agent_key")
@click.option("--project", default=".", help="Project root")
def invoke_agent(agent_key: str, project: str):
    """
    Invoke a SaxoFlow agent for the current tutoring step.

    AGENT_KEY must be a registered agent: rtlgen, tbgen, rtlreview,
    tbreview, sim, fullpipeline, etc.
    """
    session = _require_session()
    if not session:
        return
    step = session.current_step
    # Find matching invocation in step definition
    inv = next((i for i in step.agent_invocations if i.agent_key == agent_key), None)
    if inv is None:
        click.secho(f"Agent '{agent_key}' is not declared for this step.", fg="red")
        available = [i.agent_key for i in step.agent_invocations]
        if available:
            click.echo(f"Available agents for this step: {', '.join(available)}")
        return
    from .agent_dispatcher import dispatch_agent
    click.echo(f"Invoking {agent_key}...")
    result = dispatch_agent(inv, session, project_root=project)
    click.echo(result[:2000])  # show first 2000 chars
    click.secho(f"\n[OK] Agent result stored. Run 'teach check' to validate.", fg="green")
```

---

## 13. Phase 8 — ETH Zurich Pack (Day 2 Afternoon)

Create the pack skeleton. PDF goes under `packs/ethz_ic_design/docs/` and is never committed to git (add `packs/*/docs/*.pdf` to `.gitignore`).

### `packs/ethz_ic_design/pack.yaml`

```yaml
id: ethz_ic_design
name: "ETH Zurich IC Design Tutorial"
version: "1.0"
authors: ["ETH Zurich IIS"]
description: >
  End-to-end IC design flow from specification to GDS,
  covering RTL design, simulation, synthesis, formal verification,
  FPGA implementation, and ASIC backend.
docs:
  - filename: ethz_ic_tutorial.pdf
    type: pdf
lessons:
  - 01_setup.yaml
  - 02_rtl_design.yaml
  - 03_simulation.yaml
  - 04_waveform.yaml
  - 05_synthesis.yaml
  - 06_formal_verification.yaml
  - 07_fpga_pnr.yaml
  - 08_asic_backend.yaml
```

### Pack lessons (abbreviated — expand after PDF is obtained)

**`01_setup.yaml`** — Environment setup, tool verification  
**`02_rtl_design.yaml`** — Writing Verilog, using RTLGenAgent optionally  
**`03_simulation.yaml`** — Icarus simulation, testbench, TBGenAgent  
**`04_waveform.yaml`** — GTKWave, signal inspection  
**`05_synthesis.yaml`** — Yosys, synthesis reports, netlist inspection  
**`06_formal_verification.yaml`** — SymbiYosys, SVA properties, FormalPropGenAgent  
**`07_fpga_pnr.yaml`** — nextpnr, ECP5/ICE40 targets, bitstream generation  
**`08_asic_backend.yaml`** — OpenROAD, KLayout, GDS viewing  

Each lesson YAML follows the schema defined in Phase 1. The critical ones to complete before the demo are steps 01–04 (enough to show the full teaching flow from docs → interactive tutoring → simulation validation).

---

## 14. Phase 9 — TUI Routing Integration (Day 2 Evening)

### Step 14.1 — Create `saxoflow/teach/_tui_bridge.py`

This thin adapter connects the `cool_cli` TUI to the teach subsystem. It is the only coupling point between these two packages.

```python
# saxoflow/teach/_tui_bridge.py
"""
Adapter between cool_cli TUI and the teach subsystem.
Keeps the dependency direction clean: cool_cli never imports teach directly.
"""
from __future__ import annotations
from typing import Union
from rich.text import Text
from .session import TeachSession
from saxoflow_agenticai.core.agent_manager import AgentManager


def handle_teach_input(user_input: str, session: TeachSession) -> Union[Text, str]:
    """
    Route a student's TUI input during a teach session to TutorAgent.
    Returns a Rich-renderable for the TUI to display.
    """
    # Handle built-in teach shortcuts
    stripped = user_input.strip().lower()
    if stripped in ("next", "teach next"):
        return _handle_next(session)
    if stripped in ("check", "teach check"):
        return _handle_check(session)
    if stripped in ("status", "teach status"):
        return _handle_status(session)

    # Default: route to TutorAgent
    agent = AgentManager.get_agent("tutor")
    response = agent.run(user_input, session)
    return Text(response)


def _handle_next(session: TeachSession) -> Text:
    if not session.checks_passed.get(session.current_step.id, False):
        return Text("Current step checks not passed yet. Type 'check' to verify.", style="yellow")
    if session.advance():
        step = session.current_step
        return Text(f"Step {session.current_step_index + 1}/{session.total_steps}: {step.title}\n\n{step.goal}", style="cyan")
    return Text("All steps complete. Well done.", style="green")


def _handle_check(session: TeachSession) -> Text:
    from pathlib import Path
    from .checks import run_all_checks
    results = run_all_checks(session.current_step, session, Path("."))
    lines = []
    for passed, msg in results:
        lines.append(msg)
    return Text("\n".join(lines))


def _handle_status(session: TeachSession) -> Text:
    step = session.current_step
    passed = session.checks_passed.get(step.id, False)
    return Text(
        f"Step {session.current_step_index + 1}/{session.total_steps}: {step.title}\n"
        f"Goal: {step.goal}\n"
        f"Status: {'[PASS]' if passed else '[pending]'}"
    )
```

### Step 14.2 — Add `tutor_panel()` to `cool_cli/panels.py`

```python
# In cool_cli/panels.py — append one new function

def tutor_panel(renderable, width: int = None) -> Panel:
    """Panel for tutor responses — distinct gold border."""
    width = width or _default_panel_width()
    return Panel(
        _coerce_text(renderable),
        border_style="gold1",
        title="[bold gold1]SaxoFlow Tutor[/bold gold1]",
        width=width,
        padding=(0, 1),
    )
```

### Step 14.3 — Add teach commands to TUI completer

In `cool_cli/app.py`, add to the `_build_completer` commands list:
```python
"teach", "teach start", "teach next", "teach check", "teach status",
"teach run", "teach ask", "teach prev", "teach quit", "teach invoke-agent",
```

---

## 15. Phase 10 — Scaling Path (Post-Demo)

These are deliberate non-goals for the 2-day build. They are listed here so the foundation is built to accommodate them without rework.

### 10.1 Embeddings Retrieval Upgrade

Replace `BM25Okapi` in `DocIndex.retrieve()` with `sentence-transformers` cosine similarity or a proper vector store (Chroma, FAISS, Qdrant). The `retrieve_chunks()` interface in `retrieval.py` does not change. Callers are unaffected.

Packages to add: `sentence-transformers`, `chromadb` or `faiss-cpu`.

### 10.2 Multi-Document Packs

`pack.yaml` already supports multiple `docs` entries. `DocIndex.build()` iterates all docs and tags each chunk with its source filename. Pass: change nothing architectural.

### 10.3 New Agent Types in Tutoring Steps

Any agent added to `AgentManager.AGENT_MAP` is immediately available in `agent_invocations` in step YAML. No changes to `agent_dispatcher.py` needed for agents that accept `(spec, ...)` style inputs. For new agent patterns, add a new dispatch branch in `_run_single_agent()`.

Example future agents available via this infrastructure:
- `synth_agent` — LLM-guided synthesis report analysis
- `timing_agent` — timing closure assistant
- `pnr_agent` — placement and routing guidance

### 10.4 VSCode Extension Integration

The `TeachSession` singleton in `state.py` can be exposed via a JSON API (a thin `teach status --json` flag) that a VSCode extension polls. The step YAML schema, checks framework, and progress tracking need zero changes.

### 10.5 Student Progress Analytics

`TeachSession.checks_passed`, `agent_results`, and `conversation_turns` already capture all data needed for:
- step completion rate
- time-to-completion per step
- number of `ask` interactions per step
- agent invocation success rate

Add a `teach report --session <id>` command that reads the persisted JSON and produces a summary.

### 10.6 Interactive Quiz Steps

Add `quiz` as a new step kind in `StepDef`. The tutor prompt for quiz steps retrieves doc chunks and formulates questions. The student's answer is evaluated by the tutor against the retrieved excerpts. No infrastructure changes needed — the `run()` call signature is identical; only the prompt template changes.

### 10.7 Pack Authoring Helper

```
saxoflow teach pack init          # scaffold pack.yaml + lessons/
saxoflow teach pack lint          # validate all YAML files against schema
saxoflow teach pack preview       # render one step as rich output, no session needed
```

---

## 16. Files Modified in Existing Codebase

| File | Change | Lines affected |
|---|---|---|
| `saxoflow/cli.py` | Add `from saxoflow.teach.cli import teach` + `cli.add_command(teach)` | +3 lines |
| `cool_cli/state.py` | Add `teach_session: Optional[TeachSession] = None` + `__all__` entry + `reset_state()` line | +6 lines |
| `cool_cli/app.py` | Add teach-mode routing guard in main loop | +8 lines |
| `cool_cli/panels.py` | Add `tutor_panel()` function | +12 lines |
| `cool_cli/app.py` | Add teach commands to `_build_completer()` | +4 lines |
| `saxoflow_agenticai/core/agent_manager.py` | Add `"tutor"` entry to `AGENT_MAP` | +1 line |

**No existing function signatures are changed. No existing behavior is modified.**

---

## 17. New Dependencies

| Package | Purpose | Install |
|---|---|---|
| `pypdf` | PDF text extraction | `pip install pypdf` |
| `rank-bm25` | BM25 retrieval | `pip install rank-bm25` |

Both are pure Python, no system dependencies, no CUDA, no external servers. Add both to `requirements.txt`.

Future (Phase 10 only):
- `sentence-transformers` — dense embeddings upgrade
- `chromadb` or `faiss-cpu` — vector store upgrade

---

## 18. Non-Negotiable Architecture Rules

These rules must be enforced in code review for every contribution to the teach subsystem:

1. **`TeachSession` is always injected into `TutorAgent.run()`.** It is never reconstructed from disk mid-session. It is never passed as `**kwargs`. It is always the first explicit argument after `self`.

2. **The LLM never decides which command to execute.** `runner.py` executes only commands from step YAML. `TutorAgent` explains commands. `_tui_bridge.py` routes explicit shortcuts. These are three separate code paths that never mix.

3. **`retrieve_chunks()` is the only retrieval call site in `TutorAgent`.** Never call `DocIndex` or `BM25Okapi` directly from `TutorAgent`. The BM25 → embeddings upgrade happens in `retrieval.py` and nowhere else.

4. **`agent_dispatcher.py` dispatches only agents registered in `AgentManager.AGENT_MAP`.** Never import agent classes directly from `agent_dispatcher.py`. Always go through `AgentManager.get_agent(key)`.

5. **All context to the LLM comes from `_build_context_bundle()`.** No context is constructed elsewhere and merged in. The bundle is a single deterministic function call.

6. **Pack YAML is the only place commands are declared.** No hardcoded tool commands anywhere in `teach/`. Commands in YAML → resolved by `command_map.py` → executed by `runner.py`. This is the full pipeline.

7. **`_tui_bridge.py` is the only file in `saxoflow/teach/` that imports from `cool_cli`.** Keep the dependency direction: `cool_cli` → `teach`, never `teach` → `cool_cli` except through the bridge.

---

## 19. SMACD Paper Revision Angle

**New abstract claim** (replaces current architecture-description framing):

> SaxoFlow introduces a document-grounded interactive tutoring mode enabling any structured EDA tutorial to become a step-bounded interactive course. A four-layer deterministic context bundle — step definition, retrieved document excerpts, workspace state, and conversation history — is composed into every LLM call, preventing context drift across heterogeneous student interactions. A command translation registry maps native open-source tool invocations to SaxoFlow wrappers deterministically. The complete agent catalog (RTL generation, testbench generation, formal property generation, simulation, review, and debugging) is accessible from within any tutoring step, bridging document-oriented instruction with AI-assisted design generation.

**Competition criteria coverage** (SMACD EDA):

| Criterion | Coverage |
|---|---|
| Complexity of problem | Multi-layer context composition; document indexing; agent dispatch |
| Level of automation | End-to-end: doc → index → step → command → check → agent → heal |
| Designer interface | TUI with teach mode; natural language interaction; Rich panels |
| Applicability | Any PDF tutorial from any university; generic pack format |
| Robustness | Deterministic command execution; LLM explains, does not execute |
| Integration degree | 14 open-source EDA tools; 9 existing agents; all accessible from tutoring |

**ETH Zurich connection**: SaxoFlow is a TU Dresden student initiative; ETH Zurich is the source of the first teaching pack. TU Dresden and ETH Zurich are both active in the SMACD community. This geographic and institutional relevance is a legitimate advantage in positioning.

---

*Plan version: 1.0 — March 2026*  
*Prepared from: SaxoFlow codebase analysis + architectural review*  
*Status: Ready for implementation*
