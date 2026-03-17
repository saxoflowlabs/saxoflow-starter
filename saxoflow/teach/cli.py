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

import logging
import os
import sys
from pathlib import Path

import click

logger = logging.getLogger("saxoflow.teach.cli")

# Default location where teaching packs live, relative to CWD.
_DEFAULT_PACKS_DIR = Path("packs")


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
