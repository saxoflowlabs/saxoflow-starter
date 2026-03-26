# saxoflow/teach/cli.py
"""
Click command group for the SaxoFlow interactive tutoring subsystem.

Registered under ``saxoflow teach`` in ``saxoflow/cli.py``.

Sub-commands
------------
``saxoflow teach start <pack_id>``
    Load a teaching pack and enter interactive tutor mode.

``saxoflow teach index <pack_id>``
    (Re-)build the document index for a pack.

``saxoflow teach list``
    List all available packs in the default packs directory.

``saxoflow teach status``
    Show progress for the currently active (or saved) teach session.

Python: 3.9+
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from pathlib import Path

import click

logger = logging.getLogger("saxoflow.teach.cli")

# Default location where teaching packs live, relative to CWD.
_DEFAULT_PACKS_DIR = Path("packs")
_M5_TRANSITION_SHIM_WARNING = (
    "[M5 transition shim] Migrating legacy pack format on the fly. "
    "Use 'saxoflow teach import' + 'saxoflow teach build' to produce canonical artifacts."
)


def _emit_m5_transition_warning() -> None:
    """Emit a one-line transition warning when legacy migration shim is used."""
    click.echo(_M5_TRANSITION_SHIM_WARNING)


def _collect_canonical_coverage(pack_path: Path) -> tuple[int, int]:
    """Return ``(with_canonical_action, total_steps)`` for a built pack."""
    from saxoflow.teach.pack import load_pack  # noqa: PLC0415

    pack = load_pack(pack_path)
    total = len(pack.steps)
    with_canonical = sum(1 for step in pack.steps if getattr(step, "canonical_action", None))
    return with_canonical, total


def _spec_to_dict(spec) -> dict:
    """Serialize TutorialSpec to a JSON/YAML-friendly dictionary."""
    return {
        "schema_version": spec.schema_version,
        "id": spec.id,
        "name": spec.name,
        "version": spec.version,
        "authors": list(spec.authors),
        "description": spec.description,
        "docs": list(spec.docs),
        "docs_dir": str(spec.docs_dir),
        "pack_path": str(spec.pack_path),
        "steps": [
            {
                "id": s.id,
                "title": s.title,
                "goal": s.goal,
                "read": list(s.read),
                "canonical_action": s.canonical_action,
                "commands": [
                    {
                        "native": c.native,
                        "preferred": c.preferred,
                        "use_preferred_if_available": c.use_preferred_if_available,
                        "background": c.background,
                    }
                    for c in s.commands
                ],
                "agent_invocations": [
                    {
                        "agent_key": a.agent_key,
                        "args": dict(a.args),
                        "description": a.description,
                    }
                    for a in s.agent_invocations
                ],
                "success": [
                    {"kind": chk.kind, "pattern": chk.pattern, "file": chk.file}
                    for chk in s.success
                ],
                "hints": list(s.hints),
                "questions": [
                    {
                        "text": q.text,
                        "after_command": q.after_command,
                        "kind": q.kind,
                    }
                    for q in s.questions
                ],
                "notes": s.notes,
                "mode": s.mode,
                "grading_safe": s.grading_safe,
            }
            for s in spec.steps
        ],
    }


def _spec_from_dict(raw: dict):
    """Deserialize a dictionary into TutorialSpec dataclasses."""
    from saxoflow.teach.session import AgentInvocationDef, CheckDef, CommandDef, QuestionDef  # noqa: PLC0415
    from saxoflow.teach.tutorialspec import TutorialSpec, TutorialStep  # noqa: PLC0415

    steps = []
    for step in raw.get("steps", []):
        steps.append(
            TutorialStep(
                id=str(step["id"]),
                title=str(step.get("title", "")),
                goal=str(step.get("goal", "")),
                read=list(step.get("read", [])),
                canonical_action=step.get("canonical_action"),
                commands=[
                    CommandDef(
                        native=str(c["native"]),
                        preferred=(str(c["preferred"]) if c.get("preferred") else None),
                        use_preferred_if_available=bool(c.get("use_preferred_if_available", True)),
                        background=bool(c.get("background", False)),
                    )
                    for c in step.get("commands", [])
                ],
                agent_invocations=[
                    AgentInvocationDef(
                        agent_key=str(a["agent_key"]),
                        args={str(k): str(v) for k, v in dict(a.get("args", {})).items()},
                        description=str(a.get("description", "")),
                    )
                    for a in step.get("agent_invocations", [])
                ],
                success=[
                    CheckDef(
                        kind=str(chk["kind"]),
                        pattern=str(chk.get("pattern", "")),
                        file=str(chk.get("file", "")),
                    )
                    for chk in step.get("success", [])
                ],
                hints=[str(h) for h in step.get("hints", [])],
                questions=[
                    QuestionDef(
                        text=str(q["text"]),
                        after_command=int(q.get("after_command", -1)),
                        kind=str(q.get("kind", "reflection")),
                    )
                    for q in step.get("questions", [])
                ],
                notes=str(step.get("notes", "")),
                mode=str(step.get("mode", "sequential")),
                grading_safe=bool(step.get("grading_safe", False)),
            )
        )

    return TutorialSpec(
        schema_version=str(raw.get("schema_version", "1.0")),
        id=str(raw["id"]),
        name=str(raw.get("name", raw["id"])),
        version=str(raw.get("version", "1.0")),
        authors=[str(a) for a in raw.get("authors", [])],
        description=str(raw.get("description", "")),
        docs=list(raw.get("docs", [])),
        steps=steps,
        docs_dir=Path(str(raw.get("docs_dir", "."))),
        pack_path=Path(str(raw.get("pack_path", "."))),
    )


def _load_tutorialspec_file(spec_path: Path):
    """Load TutorialSpec from YAML/JSON authored artifact."""
    import yaml  # noqa: PLC0415

    if not spec_path.exists():
        raise FileNotFoundError(f"Tutorial spec not found: {spec_path}")
    text = spec_path.read_text(encoding="utf-8")
    if spec_path.suffix.lower() == ".json":
        raw = json.loads(text)
    else:
        raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError("Tutorial spec must contain a top-level mapping.")
    return _spec_from_dict(raw)


def _write_tutorialspec_file(spec, out_path: Path) -> None:
    """Write TutorialSpec as YAML or JSON based on filename suffix."""
    import yaml  # noqa: PLC0415

    payload = _spec_to_dict(spec)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() == ".json":
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    else:
        out_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Top-level group
# ---------------------------------------------------------------------------


@click.group("teach")
def teach_group() -> None:
    """Interactive document-grounded tutoring for EDA design flows."""


# ---------------------------------------------------------------------------
# teach list
# ---------------------------------------------------------------------------


@teach_group.command("list")
@click.option(
    "--packs-dir",
    default=None,
    help="Directory containing teaching packs (default: ./packs).",
    type=click.Path(file_okay=False, dir_okay=True, exists=False),
)
def teach_list(packs_dir: str | None) -> None:
    """List all available teaching packs."""
    packs_path = Path(packs_dir) if packs_dir else _DEFAULT_PACKS_DIR

    if not packs_path.exists():
        click.echo(f"No packs directory found at: {packs_path}")
        click.echo("Create a teaching pack in ./packs/<pack_id>/pack.yaml")
        return

    found = [d for d in sorted(packs_path.iterdir()) if (d / "pack.yaml").exists()]
    if not found:
        click.echo(f"No packs found in {packs_path}")
        return

    click.echo(f"Available packs in {packs_path}:")
    for pack_dir in found:
        try:
            import yaml  # noqa: PLC0415

            raw = yaml.safe_load((pack_dir / "pack.yaml").read_text(encoding="utf-8"))
            name = raw.get("name", pack_dir.name)
            version = raw.get("version", "?")
            steps = len(raw.get("lessons", []))
            click.echo(f"  {pack_dir.name:25s}  {name} v{version}  ({steps} steps)")
        except Exception:  # pragma: no cover
            click.echo(f"  {pack_dir.name:25s}  (could not parse pack.yaml)")


# ---------------------------------------------------------------------------
# teach index
# ---------------------------------------------------------------------------


@teach_group.command("index")
@click.argument("pack_id")
@click.option(
    "--packs-dir",
    default=None,
    help="Root directory containing teaching packs.",
    type=click.Path(file_okay=False, dir_okay=True, exists=False),
)
@click.option("--force", is_flag=True, help="Rebuild index even if it exists.")
def teach_index(pack_id: str, packs_dir: str | None, force: bool) -> None:
    """Build (or rebuild) the document index for PACK_ID."""
    from saxoflow.teach.pack import load_pack, PackLoadError  # noqa: PLC0415
    from saxoflow.teach.indexer import DocIndex, IndexBuildError  # noqa: PLC0415
    from saxoflow.teach.retrieval import invalidate_cache  # noqa: PLC0415

    packs_path = Path(packs_dir) if packs_dir else _DEFAULT_PACKS_DIR
    pack_path = packs_path / pack_id

    try:
        pack = load_pack(pack_path)
    except (FileNotFoundError, PackLoadError) as exc:
        click.echo(f"Error loading pack '{pack_id}': {exc}", err=True)
        raise SystemExit(1) from exc

    idx = DocIndex(pack)

    if force:
        invalidate_cache(pack_id)
        idx_path = idx._index_path
        if idx_path.exists():
            idx_path.unlink()
            click.echo(f"Removed existing index for '{pack_id}'.")

    try:
        idx.build()
        click.echo(
            f"Index built for pack '{pack_id}': {idx.chunk_count} chunks."
        )
    except IndexBuildError as exc:
        click.echo(f"Index build error: {exc}", err=True)
        raise SystemExit(1) from exc


# ---------------------------------------------------------------------------
# teach start
# ---------------------------------------------------------------------------


@teach_group.command("start")
@click.argument("pack_id")
@click.option(
    "--packs-dir",
    default=None,
    help="Root directory containing teaching packs.",
    type=click.Path(file_okay=False, dir_okay=True, exists=False),
)
@click.option(
    "--project-root",
    default=".",
    help="Working directory for running step commands.",
    type=click.Path(file_okay=False, dir_okay=True, exists=False),
)
@click.option("--resume", is_flag=True, default=True, help="Resume saved progress (default on).")
@click.option("--provider", default=None, help="LLM provider override.")
@click.option("--model", default=None, help="LLM model name override.")
@click.option("--verbose", is_flag=True, help="Verbose LLM logging.")
def teach_start(
    pack_id: str,
    packs_dir: str | None,
    project_root: str,
    resume: bool,
    provider: str | None,
    model: str | None,
    verbose: bool,
) -> None:
    """Load PACK_ID and enter interactive tutor mode in the SaxoFlow TUI.

    This command loads the pack and sets ``cool_cli.state.teach_session`` so
    the TUI's routing guard (app.py) intercepts all subsequent input and
    routes it through the tutoring pipeline.

    If the TUI is not running, falls back to a minimal readline loop.
    """
    from saxoflow.teach.pack import load_pack, PackLoadError  # noqa: PLC0415
    from saxoflow.teach.session import TeachSession  # noqa: PLC0415
    from saxoflow.teach._tui_bridge import start_session_panel  # noqa: PLC0415
    from saxoflow.teach.indexer import DocIndex  # noqa: PLC0415

    packs_path = Path(packs_dir) if packs_dir else _DEFAULT_PACKS_DIR
    pack_path = packs_path / pack_id

    # --- Load pack -----------------------------------------------------------
    try:
        pack = load_pack(pack_path)
    except (FileNotFoundError, PackLoadError) as exc:
        click.echo(f"Error loading pack '{pack_id}': {exc}", err=True)
        raise SystemExit(1) from exc

    # --- Ensure index exists --------------------------------------------------
    idx = DocIndex(pack)
    try:
        idx.load_or_build()
        click.echo(f"Index ready: {idx.chunk_count} chunks.")
    except Exception as exc:
        click.echo(
            f"Warning: could not build index ({exc}). "
            "Tutor will run without document context.",
            err=True,
        )

    # --- Build LLM -----------------------------------------------------------
    llm = None
    try:
        from saxoflow_agenticai.core.model_selector import ModelSelector  # noqa: PLC0415

        llm = ModelSelector.get_model(
            agent_type="tutor",
            provider=provider,
            model_name=model,
        )
        click.echo(f"LLM ready: {type(llm).__name__}")
    except Exception as exc:
        click.echo(
            f"Warning: could not initialize LLM ({exc}). "
            "Explanations will be unavailable until configured.",
            err=True,
        )

    # --- Create session ------------------------------------------------------
    session = TeachSession(pack=pack)
    if resume and not session.load_progress():
        click.echo("No saved progress found — starting from step 1.")

    # --- Wire into TUI if running -------------------------------------------
    try:
        from cool_cli import state as _cool_state  # noqa: PLC0415

        _cool_state.teach_session = session
        _cool_state._teach_llm = llm  # type: ignore[attr-defined]
        click.echo(
            f"Tutor session activated for pack '{pack.name}'.  "
            "Return to the TUI and start typing!"
        )
    except ImportError:
        # cool_cli not available (e.g., running standalone).
        # Fall back to a minimal readline loop.
        _run_minimal_loop(session, llm, Path(project_root), verbose)


# ---------------------------------------------------------------------------
# teach status
# ---------------------------------------------------------------------------


@teach_group.command("status")
@click.option(
    "--packs-dir",
    default=None,
    help="Root directory containing teaching packs.",
    type=click.Path(file_okay=False, dir_okay=True, exists=False),
)
def teach_status(packs_dir: str | None) -> None:
    """Show progress for the active or most recently saved teach session."""
    try:
        from cool_cli import state as _cool_state  # noqa: PLC0415

        session = _cool_state.teach_session
        if session is None:
            click.echo("No active teach session.")
        else:
            step = session.current_step
            click.echo(f"Pack:  {session.pack.name}")
            click.echo(
                f"Step:  {session.current_step_index + 1} / {session.total_steps}"
            )
            click.echo(f"Title: {step.title if step else '(complete)'}")
            click.echo(f"Checks passed: {len(session.checks_passed)}")
    except ImportError:
        click.echo("cool_cli not available — cannot read session state.")



# ---------------------------------------------------------------------------
# teach debug-images
# ---------------------------------------------------------------------------


@teach_group.command("debug-images")
@click.argument("pack_id")
@click.option(
    "--packs-dir",
    default=None,
    help="Root directory containing teaching packs.",
    type=click.Path(file_okay=False, dir_okay=True, exists=False),
)
@click.option(
    "--force-rebuild",
    is_flag=True,
    help="Force a fresh index rebuild before running diagnostics.",
)
def teach_debug_images(pack_id: str, packs_dir: str | None, force_rebuild: bool) -> None:
    """Diagnose image rendering for PACK_ID and render a test image.

    Checks:
    \b
      1. chafa binary on PATH
      2. Index contains image data  (rebuild with --force-rebuild if empty)
      3. Renders the first extracted image — shows output or error detail
    """
    import shutil as _shutil  # noqa: PLC0415
    from saxoflow.teach.pack import load_pack, PackLoadError  # noqa: PLC0415
    from saxoflow.teach.indexer import DocIndex, IndexBuildError  # noqa: PLC0415
    from saxoflow.teach._image_render import render_image_from_bytes  # noqa: PLC0415

    sep = "─" * 60

    # ── 1. chafa ──────────────────────────────────────────────────────────
    click.echo(sep)
    click.echo("STEP 1 — chafa binary")
    chafa_path = _shutil.which("chafa")
    if chafa_path:
        import subprocess as _sp  # noqa: PLC0415
        ver = _sp.run(
            [chafa_path, "--version"],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        version_line = (ver.stdout or ver.stderr or "").splitlines()[0] if (ver.stdout or ver.stderr) else "(unknown)"
        click.secho(f"  ✓  Found: {chafa_path}", fg="green")
        click.secho(f"     Version: {version_line}", fg="green")
    else:
        click.secho("  ✗  chafa not found on PATH", fg="red")
        click.secho(f"     PATH={os.environ.get('PATH', '(not set)')}", fg="yellow")
        click.secho("     Fix: saxoflow install --single chafa", fg="yellow")
        click.echo(sep)
        raise SystemExit(1)

    # ── 2. pack + index ───────────────────────────────────────────────────
    click.echo(sep)
    click.echo("STEP 2 — pack & index")
    packs_path = Path(packs_dir) if packs_dir else _DEFAULT_PACKS_DIR
    pack_path = packs_path / pack_id
    try:
        pack = load_pack(pack_path)
        click.secho(f"  ✓  Pack loaded: {pack.name}", fg="green")
    except Exception as exc:
        click.secho(f"  ✗  Pack load failed: {exc}", fg="red")
        raise SystemExit(1) from exc

    idx = DocIndex(pack)

    if force_rebuild:
        from saxoflow.teach.retrieval import invalidate_cache  # noqa: PLC0415
        invalidate_cache(pack_id)
        if idx._index_path.exists():
            idx._index_path.unlink()
            click.echo("  ↻  Removed stale index — rebuilding …")

    try:
        idx.load_or_build()
        click.secho(f"  ✓  Index ready: {idx.chunk_count} chunks", fg="green")
    except IndexBuildError as exc:
        click.secho(f"  ✗  Index build failed: {exc}", fg="red")
        raise SystemExit(1) from exc

    # Summarise image_map
    image_map = idx._image_map  # type: ignore[attr-defined]
    total_images = sum(len(v) for v in image_map.values())
    if total_images == 0:
        click.secho(
            "  ✗  image_map is EMPTY — no images found in the index.",
            fg="red",
        )
        click.secho(
            "     This usually means the index was built before the pymupdf migration.",
            fg="yellow",
        )
        click.secho(
            f"     Fix: saxoflow teach index {pack_id} --force   (then re-run this command)",
            fg="yellow",
        )
        click.echo(sep)
        raise SystemExit(1)

    click.secho(
        f"  ✓  image_map: {total_images} images across {len(image_map)} page(s)",
        fg="green",
    )
    for (doc, pg), imgs in sorted(image_map.items()):
        click.echo(f"       {doc}  p.{pg}  →  {len(imgs)} image(s)  "
                   f"({', '.join(f'{im.image_ext} {len(im.image_bytes)//1024}KB' for im in imgs)})")

    # ── 3. render first image ─────────────────────────────────────────────
    click.echo(sep)
    click.echo("STEP 3 — render first image with chafa")
    first_key = sorted(image_map.keys())[0]
    first_img = image_map[first_key][0]
    click.echo(f"  Source: {first_img.source_doc}  p.{first_img.page_num}  "
               f"ext={first_img.image_ext}  size={len(first_img.image_bytes)//1024}KB")

    art = render_image_from_bytes(
        first_img.image_bytes,
        image_ext=first_img.image_ext,
        fig_num=1,
    )

    # Check what we got back
    if "image not rendered" in art:
        click.secho("  ✗  render_image_from_bytes returned placeholder — chafa failed silently.", fg="red")
        click.secho("     Enable debug logging with SAXOFLOW_LOG_LEVEL=DEBUG to see chafa stderr.", fg="yellow")
        click.echo(art)
    else:
        click.secho("  ✓  Rendered successfully.  Preview:", fg="green")
        click.echo(art)

    click.echo(sep)


# ---------------------------------------------------------------------------
# Minimal fallback loop (no TUI)
# ---------------------------------------------------------------------------


def _run_minimal_loop(
    session,
    llm,
    project_root: Path,
    verbose: bool,
) -> None:
    """Simple readline loop for running the tutor outside of the TUI."""
    # Guard: if stdout/stdin are not connected to a real terminal we are
    # running inside a captured subprocess (e.g. the TUI's process_command).
    # Blocking on input() would deadlock invisibly, so bail out early with a
    # helpful hint instead.
    if not sys.stdin.isatty():
        click.echo(
            "Note: 'saxoflow teach start' must be run inside the SaxoFlow TUI "
            "interactive shell, not as a captured subprocess.\n"
            "Start the TUI with 'saxoflow app' (or 'python3 saxoflow.py') and "
            "type 'saxoflow teach start <pack_id>' at the prompt.",
            err=True,
        )
        return
    from saxoflow.teach._tui_bridge import handle_input, start_session_panel  # noqa: PLC0415
    from rich.console import Console as _Console  # noqa: PLC0415

    con = _Console()
    con.print(start_session_panel(session))

    while True:
        try:
            user_input = input("tutor> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            continue

        panel = handle_input(
            user_input, session, str(project_root), llm=llm, verbose=verbose
        )
        con.print(panel)

        if user_input.lower() == "quit":
            break
        if session.is_complete:
            break

    session.save_progress()
    click.echo("Progress saved.")


# ---------------------------------------------------------------------------
# teach import  (M5)
# ---------------------------------------------------------------------------


@teach_group.command("import")
@click.argument("source")
@click.option(
    "--output",
    "output_path",
    default=None,
    help="Output TutorialSpec file (.yaml/.yml/.json).",
    type=click.Path(file_okay=True, dir_okay=False, exists=False),
)
def teach_import(source: str, output_path: str | None) -> None:
    """Ingest SOURCE into a TutorialSpec authoring artifact.

    SOURCE may be:
    - a legacy pack directory (contains pack.yaml), or
    - a single document (.md/.pdf/.txt) to scaffold a draft spec.
    """
    from saxoflow.teach.tutorialspec import LegacyPackMigrator, TUTORIALSPEC_VERSION, TutorialSpec, TutorialStep  # noqa: PLC0415

    src = Path(source).resolve()

    if src.is_dir() and (src / "pack.yaml").exists():
        _emit_m5_transition_warning()
        spec, report = LegacyPackMigrator().migrate(src)
        out = Path(output_path) if output_path else Path(f"{spec.id}.tutorialspec.yaml")
        _write_tutorialspec_file(spec, out)
        click.echo(f"Imported legacy pack '{spec.id}' -> {out}")
        if report.warnings:
            click.echo(f"Migration warnings: {len(report.warnings)} (run 'teach validate' for details)")
        return

    if src.is_file() and src.name == "pack.yaml":
        _emit_m5_transition_warning()
        spec, report = LegacyPackMigrator().migrate(src.parent)
        out = Path(output_path) if output_path else Path(f"{spec.id}.tutorialspec.yaml")
        _write_tutorialspec_file(spec, out)
        click.echo(f"Imported legacy pack '{spec.id}' -> {out}")
        if report.warnings:
            click.echo(f"Migration warnings: {len(report.warnings)} (run 'teach validate' for details)")
        return

    if src.is_file() and src.suffix.lower() in {".md", ".pdf", ".txt"}:
        spec = TutorialSpec(
            schema_version=TUTORIALSPEC_VERSION,
            id=src.stem.replace(" ", "_").lower(),
            name=f"Imported tutorial: {src.stem}",
            version="1.0",
            authors=[],
            description=f"Draft imported from {src.name}",
            docs=[{"filename": src.name, "type": src.suffix.lstrip(".")}],
            steps=[
                TutorialStep(
                    id="step_1",
                    title="Introduction",
                    goal="Review the imported source and draft learning steps.",
                    read=[{"doc": src.name, "pages": "1", "section": ""}],
                )
            ],
            docs_dir=src.parent,
            pack_path=src.parent,
        )
        out = Path(output_path) if output_path else Path(f"{spec.id}.tutorialspec.yaml")
        _write_tutorialspec_file(spec, out)
        click.echo(f"Imported source '{src.name}' -> {out}")
        return

    click.echo(
        "Unsupported source. Provide a legacy pack directory/pack.yaml or a .md/.pdf/.txt file.",
        err=True,
    )
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# teach build  (M5)
# ---------------------------------------------------------------------------


@teach_group.command("build")
@click.argument("tutorial_spec")
@click.option(
    "--output-dir",
    default="packs",
    show_default=True,
    help="Directory where compiled pack artifacts are written.",
    type=click.Path(file_okay=False, dir_okay=True, exists=False),
)
def teach_build(tutorial_spec: str, output_dir: str) -> None:
    """Compile a TutorialSpec file into executable pack artifacts."""
    _emit_m5_transition_warning()
    import yaml  # noqa: PLC0415
    from saxoflow.teach.tutorialspec import TutorialSpecCompiler  # noqa: PLC0415

    spec_path = Path(tutorial_spec).resolve()
    try:
        spec = _load_tutorialspec_file(spec_path)
    except Exception as exc:
        click.echo(f"Failed to load tutorial spec: {exc}", err=True)
        raise SystemExit(1) from exc

    compiler = TutorialSpecCompiler()
    result = compiler.compile(spec)
    if result.issues:
        for issue in result.issues:
            icon = "✗" if issue.severity == "error" else "!"
            click.echo(f"  [{icon}] [{issue.severity}] step={issue.step_id}  "
                       f"({issue.field}): {issue.message}")
    if not result.ok:
        click.echo(result.summary(), err=True)
        raise SystemExit(1)

    root = Path(output_dir)
    pack_root = root / spec.id
    lessons_dir = pack_root / "lessons"
    docs_dir = pack_root / "docs"
    lessons_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    lesson_files = []
    for idx, step in enumerate(spec.steps, start=1):
        lesson_name = f"{idx:02d}_{step.id}.yaml"
        lesson_files.append(lesson_name)
        lesson_payload = {
            "id": step.id,
            "title": step.title,
            "goal": step.goal,
            "read": step.read,
            "canonical_action": step.canonical_action,
            "commands": [
                {
                    "native": c.native,
                    "preferred": c.preferred,
                    "use_preferred_if_available": c.use_preferred_if_available,
                    "background": c.background,
                }
                for c in step.commands
            ],
            "agent_invocations": [
                {
                    "agent_key": a.agent_key,
                    "args": dict(a.args),
                    "description": a.description,
                }
                for a in step.agent_invocations
            ],
            "success": [
                {"kind": chk.kind, "pattern": chk.pattern, "file": chk.file}
                for chk in step.success
            ],
            "hints": list(step.hints),
            "questions": [
                {
                    "text": q.text,
                    "after_command": q.after_command,
                    "kind": q.kind,
                }
                for q in step.questions
            ],
            "notes": step.notes,
            "mode": step.mode,
        }
        (lessons_dir / lesson_name).write_text(
            yaml.safe_dump(lesson_payload, sort_keys=False),
            encoding="utf-8",
        )

    pack_payload = {
        "id": spec.id,
        "name": spec.name,
        "version": spec.version,
        "authors": list(spec.authors),
        "description": spec.description,
        "docs": list(spec.docs),
        "lessons": lesson_files,
    }
    (pack_root / "pack.yaml").write_text(
        yaml.safe_dump(pack_payload, sort_keys=False),
        encoding="utf-8",
    )

    manifest_path = pack_root / "tutorialspec.build.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source_spec": str(spec_path),
                "pack_id": spec.id,
                "steps": len(spec.steps),
                "result": result.summary(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    click.echo(f"Built pack '{spec.id}' -> {pack_root}")
    click.echo(result.summary())


# ---------------------------------------------------------------------------
# teach action run  (M5 canonical runtime hook)
# ---------------------------------------------------------------------------


@teach_group.group("action")
def teach_action_group() -> None:
    """Canonical teach action namespace."""


@teach_action_group.command("run")
@click.option("--pack", "pack_id", required=True, help="Pack ID to run step from.")
@click.option("--step", "step_id", required=True, help="Step ID to execute.")
@click.option(
    "--packs-dir",
    default=None,
    help="Root directory containing teaching packs (default: ./packs).",
    type=click.Path(file_okay=False, dir_okay=True, exists=False),
)
@click.option(
    "--project-root",
    default=".",
    help="Working directory for step command execution.",
    type=click.Path(file_okay=False, dir_okay=True, exists=False),
)
def teach_action_run(
    pack_id: str,
    step_id: str,
    packs_dir: str | None,
    project_root: str,
) -> None:
    """Execute one step by canonical teach action reference."""
    from saxoflow.teach.pack import load_pack, PackLoadError  # noqa: PLC0415
    from saxoflow.teach.runner import run_step_commands  # noqa: PLC0415
    from saxoflow.teach.session import TeachSession  # noqa: PLC0415
    from saxoflow.teach.checks import evaluate_step_success  # noqa: PLC0415

    packs_path = Path(packs_dir) if packs_dir else _DEFAULT_PACKS_DIR
    pack_path = packs_path / pack_id

    try:
        pack = load_pack(pack_path)
    except (FileNotFoundError, PackLoadError) as exc:
        click.echo(f"Error loading pack '{pack_id}': {exc}", err=True)
        raise SystemExit(1) from exc

    session = TeachSession(pack=pack)
    idx = next((i for i, s in enumerate(pack.steps) if s.id == step_id), None)
    if idx is None:
        click.echo(f"Step '{step_id}' not found in pack '{pack_id}'.", err=True)
        raise SystemExit(1)

    session.current_step_index = idx
    results = run_step_commands(session, Path(project_root))
    if not results:
        click.echo("No commands declared for this step.")
        raise SystemExit(0)

    for r in results:
        click.echo(f"$ {r.command_str}")
        if r.stdout:
            click.echo(r.stdout)
        click.echo(f"exit_code={r.exit_code}")

    passed = evaluate_step_success(session, Path(project_root))
    if not passed:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# teach publish  (M5)
# ---------------------------------------------------------------------------


@teach_group.command("publish")
@click.argument("pack_id")
@click.option(
    "--packs-dir",
    default=None,
    help="Root directory containing built teaching packs (default: ./packs).",
    type=click.Path(file_okay=False, dir_okay=True, exists=False),
)
@click.option(
    "--registry-dir",
    default=".saxoflow/teach_registry",
    show_default=True,
    help="Publication registry directory.",
    type=click.Path(file_okay=False, dir_okay=True, exists=False),
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing published pack in registry.",
)
@click.option(
    "--require-build-manifest/--no-require-build-manifest",
    default=True,
    show_default=True,
    help="Require tutorialspec.build.json before publication.",
)
@click.option(
    "--require-canonical/--allow-native-fallback",
    default=True,
    show_default=True,
    help="Require every lesson step to carry canonical_action metadata.",
)
def teach_publish(
    pack_id: str,
    packs_dir: str | None,
    registry_dir: str,
    force: bool,
    require_build_manifest: bool,
    require_canonical: bool,
) -> None:
    """Publish a compiled teaching pack to the local teach registry."""
    import datetime as _dt  # noqa: PLC0415

    packs_path = Path(packs_dir) if packs_dir else _DEFAULT_PACKS_DIR
    src_pack = packs_path / pack_id
    if not (src_pack / "pack.yaml").exists():
        click.echo(f"Pack '{pack_id}' not found under {packs_path}.", err=True)
        raise SystemExit(1)

    build_manifest = src_pack / "tutorialspec.build.json"
    if require_build_manifest and not build_manifest.exists():
        click.echo(
            "Publish blocked: missing tutorialspec.build.json. "
            "Run 'saxoflow teach build <tutorialspec>' first or pass --no-require-build-manifest.",
            err=True,
        )
        raise SystemExit(1)

    with_canonical, total_steps = _collect_canonical_coverage(src_pack)
    if require_canonical and with_canonical != total_steps:
        click.echo(
            "Publish blocked: canonical coverage is incomplete "
            f"({with_canonical}/{total_steps}). Use canonical actions for all steps "
            "or pass --allow-native-fallback.",
            err=True,
        )
        raise SystemExit(1)

    dst_root = Path(registry_dir)
    dst_pack = dst_root / pack_id
    dst_root.mkdir(parents=True, exist_ok=True)

    if dst_pack.exists():
        if not force:
            click.echo(
                f"Pack '{pack_id}' is already published at {dst_pack}. Use --force to overwrite.",
                err=True,
            )
            raise SystemExit(1)
        shutil.rmtree(dst_pack)

    shutil.copytree(src_pack, dst_pack)
    manifest = {
        "pack_id": pack_id,
        "source": str(src_pack.resolve()),
        "published_to": str(dst_pack.resolve()),
        "published_at_utc": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
        "build_manifest_present": build_manifest.exists(),
        "canonical_steps": with_canonical,
        "total_steps": total_steps,
        "canonical_coverage": (with_canonical / total_steps) if total_steps else 0.0,
    }
    (dst_pack / "publish.manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    click.echo(f"Published pack '{pack_id}' -> {dst_pack}")


# ---------------------------------------------------------------------------
# teach validate  (M5)
# ---------------------------------------------------------------------------


@teach_group.command("validate")
@click.argument("pack_id")
@click.option(
    "--packs-dir",
    default=None,
    help="Root directory containing teaching packs (default: ./packs).",
    type=click.Path(file_okay=False, dir_okay=True, exists=False),
)
def teach_validate(pack_id: str, packs_dir: str | None) -> None:
    """Validate PACK_ID against the TutorialSpec v1 authoring contracts.

    Migrates the legacy pack on the fly, compiles the resulting TutorialSpec,
    and reports any validation issues.  Exit code is non-zero when errors
    are found.
    """
    from saxoflow.teach.tutorialspec import (  # noqa: PLC0415
        LegacyPackMigrator,
        TutorialSpecCompiler,
    )

    packs_path = Path(packs_dir) if packs_dir else _DEFAULT_PACKS_DIR
    pack_path = packs_path / pack_id

    _emit_m5_transition_warning()
    migrator = LegacyPackMigrator()
    try:
        spec, report = migrator.migrate(pack_path)
    except (FileNotFoundError, Exception) as exc:
        click.echo(f"Error loading pack '{pack_id}': {exc}", err=True)
        raise SystemExit(1) from exc

    if report.warnings:
        click.echo("Migration warnings:")
        for w in report.warnings:
            click.echo(f"  - {w}")

    compiler = TutorialSpecCompiler()
    result = compiler.compile(spec)

    if result.issues:
        for issue in result.issues:
            icon = "✗" if issue.severity == "error" else "!"
            click.echo(f"  [{icon}] [{issue.severity}] step={issue.step_id}  "
                       f"({issue.field}): {issue.message}")
    click.echo(result.summary())

    if not result.ok:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# teach preview  (M5)
# ---------------------------------------------------------------------------


@teach_group.command("preview")
@click.argument("pack_id")
@click.option(
    "--packs-dir",
    default=None,
    help="Root directory containing teaching packs (default: ./packs).",
    type=click.Path(file_okay=False, dir_okay=True, exists=False),
)
@click.option(
    "--step",
    "step_index",
    default=0,
    show_default=True,
    help="0-based step index to preview.",
    type=int,
)
def teach_preview(pack_id: str, packs_dir: str | None, step_index: int) -> None:
    """Preview one step of PACK_ID in the TutorialSpec v1 format."""
    from saxoflow.teach.tutorialspec import (  # noqa: PLC0415
        LegacyPackMigrator,
        TutorialSpecCompiler,
    )

    packs_path = Path(packs_dir) if packs_dir else _DEFAULT_PACKS_DIR
    pack_path = packs_path / pack_id

    _emit_m5_transition_warning()
    migrator = LegacyPackMigrator()
    try:
        spec, _report = migrator.migrate(pack_path)
    except (FileNotFoundError, Exception) as exc:
        click.echo(f"Error loading pack '{pack_id}': {exc}", err=True)
        raise SystemExit(1) from exc

    compiler = TutorialSpecCompiler()
    click.echo(compiler.preview(spec, step_index=step_index))


# ---------------------------------------------------------------------------
# teach export  (M5)
# ---------------------------------------------------------------------------


@teach_group.command("export")
@click.argument("pack_id")
@click.option(
    "--packs-dir",
    default=None,
    help="Root directory containing teaching packs (default: ./packs).",
    type=click.Path(file_okay=False, dir_okay=True, exists=False),
)
@click.option(
    "--output-dir",
    default=".",
    show_default=True,
    help="Directory to write the grading-safe JSON export.",
    type=click.Path(file_okay=False, dir_okay=True, exists=False),
)
def teach_export(pack_id: str, packs_dir: str | None, output_dir: str) -> None:
    """Export grading-safe steps of PACK_ID as JSON for automated grading.

    Only steps with ``grading_safe=True`` are included in the export.
    The output file is ``<output_dir>/<pack_id>_grading.json``.
    """
    import json  # noqa: PLC0415
    from saxoflow.teach.tutorialspec import LegacyPackMigrator  # noqa: PLC0415

    packs_path = Path(packs_dir) if packs_dir else _DEFAULT_PACKS_DIR
    pack_path = packs_path / pack_id

    _emit_m5_transition_warning()
    migrator = LegacyPackMigrator()
    try:
        spec, _report = migrator.migrate(pack_path)
    except (FileNotFoundError, Exception) as exc:
        click.echo(f"Error loading pack '{pack_id}': {exc}", err=True)
        raise SystemExit(1) from exc

    grading_steps = [s for s in spec.steps if s.grading_safe]
    if not grading_steps:
        click.echo(f"No grading-safe steps found in pack '{pack_id}'.")
        return

    export_data = {
        "schema_version": spec.schema_version,
        "pack_id": spec.id,
        "pack_name": spec.name,
        "pack_version": spec.version,
        "grading_steps": [
            {
                "id": s.id,
                "title": s.title,
                "goal": s.goal,
                "canonical_action": s.canonical_action,
                "success_checks": [
                    {"kind": c.kind, "pattern": c.pattern, "file": c.file}
                    for c in s.success
                ],
            }
            for s in grading_steps
        ],
    }

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    out_file = out_path / f"{pack_id}_grading.json"
    out_file.write_text(json.dumps(export_data, indent=2), encoding="utf-8")

    click.echo(
        f"Exported {len(grading_steps)} grading-safe step(s) → {out_file}"
    )

