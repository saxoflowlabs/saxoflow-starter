# saxoflow/teach/__init__.py
"""
SaxoFlow Interactive Tutoring Subsystem.

Provides document-grounded, step-by-step interactive tutoring for
EDA design flows.  Any structured tutorial (PDF / Markdown) can be
packaged as a teaching pack and used to guide students through a
complete IC design flow using SaxoFlow CLI commands and AI agents.

Sub-modules
-----------
session      -- TeachSession, StepDef, PackDef dataclasses (the spine)
pack         -- pack.yaml / lesson YAML loader and validator
indexer      -- PDF/MD text extraction + BM25 index builder
retrieval    -- retrieve_chunks() stable retrieval interface
command_map  -- Native tool command -> SaxoFlow wrapper translation
checks       -- Deterministic step success validators
runner       -- Step command executor (never executes AI-suggested cmds)
agent_dispatcher -- Invoke any registered agent from within a step
cli          -- Click command group: teach <subcommand>
_tui_bridge  -- Thin adapter between cool_cli TUI and the teach subsystem
"""

from saxoflow.teach.pack import load_pack, PackLoadError
from saxoflow.teach.session import (
    TeachSession,
    PackDef,
    StepDef,
    CommandDef,
    CheckDef,
    AgentInvocationDef,
)

__all__ = [
    "TeachSession",
    "PackDef",
    "StepDef",
    "CommandDef",
    "CheckDef",
    "AgentInvocationDef",
    "load_pack",
    "PackLoadError",
]
