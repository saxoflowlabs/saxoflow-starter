# cool_cli/bootstrap.py
"""
Startup bootstrap for the SaxoFlow Cool CLI.

What it does (runs once at CLI launch):
- Loads .env (if present).
- Ensures a .env file exists in the current working directory (creates a friendly template if missing).
- Resolves the provider that would actually be used right now (via ModelSelector).
- If that provider's API key env var is missing, launches an in-process native setup wizard.
- Persists the chosen provider as SAXOFLOW_LLM_PROVIDER so it overrides YAML defaults.
- Reloads .env and verifies the key; prints a clear message either way.

Non-interactive safety:
- If stdin isn't a TTY or SAXOFLOW_NONINTERACTIVE=1, it prints instructions instead of prompting,
  so CI/headless usage never blocks.
"""

from __future__ import annotations

import os
import sys
from getpass import getpass
from pathlib import Path
from typing import List, Tuple

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

__all__ = ["ensure_first_run_setup", "run_key_setup_wizard"]


# -----------------------------------------------------------------------------
# Small helpers
# -----------------------------------------------------------------------------

def _ensure_env_file_exists(cwd: Path) -> Path:
    """Create a .env in cwd if it doesn't exist, with a helpful header."""
    env_path = cwd / ".env"
    if not env_path.exists():
        env_path.write_text(
            "# SaxoFlow .env\n"
            "# Add your provider API key(s) here, e.g.:\n"
            "# OPENAI_API_KEY=sk-...\n"
            "# OPENROUTER_API_KEY=...\n"
            "# GROQ_API_KEY=...\n"
            "# MISTRAL_API_KEY=...\n"
            "# ANTHROPIC_API_KEY=...\n"
            "# GOOGLE_API_KEY=...\n"
            "# You can also override the provider/model used by SaxoFlow:\n"
            "# SAXOFLOW_LLM_PROVIDER=openai\n"
            "# SAXOFLOW_LLM_MODEL=gpt-4o\n",
            encoding="utf-8",
        )
    return env_path


def _write_env_kv(env_path: Path, key: str, value: str) -> None:
    """Idempotently set KEY=VALUE in .env, preserving other lines/comments."""
    lines: List[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    updated = False
    out: List[str] = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            out.append(line)
            continue
        k = line.split("=", 1)[0].strip()
        if k == key:
            out.append(f"{key}={value}")
            updated = True
        else:
            out.append(line)
    if not updated:
        out.append(f"{key}={value}")

    env_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def _resolve_target_provider_env() -> Tuple[str, str]:
    """
    Return (provider_name, required_env_var) for the provider that would be used now.

    Uses ModelSelector's resolution and maps provider -> env var via PROVIDERS.
    Falls back to ('openai', 'OPENAI_API_KEY') on any unexpected error.

    Deferred imports here break potential import cycles at startup.
    """
    try:
        # Deferred import (prevents circular imports)
        from saxoflow_agenticai.core.model_selector import (  # type: ignore
            ModelSelector,
            PROVIDERS,
        )
        prov, _ = ModelSelector.get_provider_and_model(agent_type=None)
        prov = (prov or "openai").strip().lower()
        env_var = PROVIDERS.get(prov, PROVIDERS["openai"]).env
    except Exception:
        prov = (os.getenv("SAXOFLOW_LLM_PROVIDER") or "openai").strip().lower()
        # Fallback mapping without importing the module again
        fallback = {
            "openai": "OPENAI_API_KEY",
            "groq": "GROQ_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "fireworks": "FIREWORKS_API_KEY",
            "together": "TOGETHER_API_KEY",
            "perplexity": "PPLX_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "dashscope": "DASHSCOPE_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            # Newly supported native providers:
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GOOGLE_API_KEY",
        }
        env_var = fallback.get(prov, "OPENAI_API_KEY")
    return prov, env_var


def _provider_env_map() -> dict:
    """Return {provider: ENV_VAR} using a deferred import (or a safe fallback)."""
    try:
        from saxoflow_agenticai.core.model_selector import PROVIDERS  # type: ignore
        return {name: spec.env for name, spec in PROVIDERS.items()}
    except Exception:
        # Keep in sync with model_selector PROVIDERS
        return {
            "dashscope": "DASHSCOPE_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "fireworks": "FIREWORKS_API_KEY",
            "groq": "GROQ_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "openai": "OPENAI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "perplexity": "PPLX_API_KEY",
            "together": "TOGETHER_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GOOGLE_API_KEY",
        }


def _has_correct_key() -> bool:
    """True if the resolved provider's required env var is set in this process."""
    _, env_var = _resolve_target_provider_env()
    return bool(os.getenv(env_var))


def _mask_tail(value: str, show: int = 4) -> str:
    """Return a masked representation of a secret, keeping the last `show` chars."""
    tail = value[-show:] if len(value) >= show else value
    return ("*" * max(0, len(value) - len(tail))) + tail


# -----------------------------------------------------------------------------
# Native, reliable wizard (no subprocess; works across terminals)
# -----------------------------------------------------------------------------

def run_key_setup_wizard(console: Console, *, preferred_provider: str | None = None) -> None:
    """
    Interactive wizard to capture provider + API key.

    - provider: typed name or index (we print an indexed list).
    - key: captured via getpass (hidden; paste works), then written to .env
      and exported to this process's environment.
    - also persists SAXOFLOW_LLM_PROVIDER=<provider> so runtime uses your choice
      even if YAML defaults to a different provider.
    """
    env_for = _provider_env_map()
    names = sorted(env_for.keys())
    preferred_provider = (preferred_provider or "openai").lower()
    env_path = _ensure_env_file_exists(Path(os.getcwd()))

    console.print(Text("\nNo LLM API key detected. Let's set one up.", style="yellow"))
    console.print("\nSupported providers:")

    for idx, name in enumerate(names, start=1):
        envv = env_for[name]
        console.print(f"  {idx}) {name:<10} (env: {envv})")

    # choose provider (name or index), default = preferred_provider
    while True:
        choice = input(
            f"\nChoose a provider ({', '.join(names)}"
            f"){f' [default: {preferred_provider}]' if preferred_provider else ''}: "
        ).strip().lower()
        if not choice and preferred_provider in names:
            provider = preferred_provider
            break
        if choice.isdigit():
            i = int(choice)
            if 1 <= i <= len(names):
                provider = names[i - 1]
                break
        if choice in names:
            provider = choice
            break
        console.print(Text("Invalid choice. Please try again.", style="red"))

    env_var = env_for[provider]

    # read key (hidden)
    console.print(Text("(input is hidden; paste works)", style="dim"))
    while True:
        api_key = getpass(f"Enter your API key for '{provider}' ({env_var}): ").strip()
        if api_key:
            break
        console.print(Text("Key cannot be empty.", style="red"))

    # persist and export
    _write_env_kv(env_path, env_var, api_key)
    os.environ[env_var] = api_key  # make it available immediately

    # Persist provider override to ensure runtime uses the selected provider
    _write_env_kv(env_path, "SAXOFLOW_LLM_PROVIDER", provider)
    os.environ["SAXOFLOW_LLM_PROVIDER"] = provider

    load_dotenv(override=True)
    console.print(
        Text(
            f"Saved {env_var}={_mask_tail(api_key)} and SAXOFLOW_LLM_PROVIDER={provider} in {env_path}.",
            style="green",
        )
    )


# -----------------------------------------------------------------------------
# Public bootstrap
# -----------------------------------------------------------------------------

def ensure_first_run_setup(console: Console) -> None:
    """
    Run at Cool CLI startup. If the chosen provider's key is missing and this is an
    interactive terminal, open the native setup wizard; otherwise print instructions.

    This function is intentionally quiet when everything is already configured.
    """
    # Load existing env values first (don't override shell exports).
    load_dotenv(override=False)

    # Make sure a .env exists where people expect to edit it.
    _ensure_env_file_exists(Path(os.getcwd()))

    # If the exact target provider key is present, we're done.
    if _has_correct_key():
        return

    prov, env_var = _resolve_target_provider_env()

    # Headless / CI mode: never block — just instruct precisely what to set.
    if not sys.stdin.isatty() or os.getenv("SAXOFLOW_NONINTERACTIVE") == "1":
        console.print(
            Panel(
                f"[yellow]No API key found for provider [bold]{prov}[/bold].[/yellow]\n"
                f"Set this environment variable before running the CLI:\n\n"
                f"    [bold]{env_var}=sk-***[/bold]\n\n"
                "Or run interactively on a TTY:\n"
                "    python -m saxoflow_agenticai.cli setupkeys",
                border_style="yellow",
                title="setup required",
            )
        )
        return

    # Interactive path: run the native wizard (reliable typing/paste).
    console.print(
        Panel(
            f"🔑 No API key found for provider [bold]{prov}[/bold].\n\n"
            "I'll open the interactive setup wizard now.\n"
            f"You can also set it manually:\n"
            f"    {env_var}=sk-***",
            border_style="cyan",
            title="setup",
        )
    )

    try:
        run_key_setup_wizard(console, preferred_provider=prov)
    except Exception as exc:  # noqa: BLE001
        console.print(Text(f"[❌] Key setup failed: {exc}", style="bold red"))
        return

    # Reload new values and verify again.
    load_dotenv(override=True)
    if _has_correct_key():
        console.print(Text("✅ LLM API key configured.", style="green"))
    else:
        console.print(Text("[❌] No API key found after setup.", style="bold red"))
