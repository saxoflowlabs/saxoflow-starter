# saxoflow_agenticai/core/prompt_manager.py
"""
Jinja2-based prompt rendering for SaxoFlow Agentic AI.

This module provides a small wrapper around Jinja2 that:
- Resolves a default prompts directory in a robust way
  (env var `SAXOFLOW_PROMPT_DIR` > caller-provided path > repo `prompts/`)
- Optionally caches compiled templates
- Surfaces friendly, explicit exceptions on missing/syntax errors
- Keeps existing, non-strict Jinja behavior (undefined variables render as "")
  to avoid changing current outputs

Public API (unchanged in spirit)
--------------------------------
- class PromptManager
    - render(template_file: str, context: Mapping[str, Any]) -> str

Python: 3.9+
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from jinja2 import (
    Environment,
    FileSystemLoader,
    TemplateNotFound,
    TemplateSyntaxError,
)

__all__ = ["PromptManager", "PromptRenderError"]

logger = logging.getLogger("saxoflow_agenticai")


class PromptRenderError(RuntimeError):
    """Raised when Jinja2 fails to render a template for any non-not-found reason."""


class PromptManager:
    """
    Thin wrapper over Jinja2 for rendering prompt templates.

    Parameters
    ----------
    template_dir : Optional[os.PathLike]
        Path to the folder containing templates. If not provided, we try:
          1) env var `SAXOFLOW_PROMPT_DIR`
          2) <repo_root>/prompts  (computed from this file's location)
    cache_templates : bool, default True
        Cache compiled templates for repeated renders. This mirrors the spirit
        of Jinja's internal caching and speeds up repeated calls.
    auto_reload : bool, default False
        If True, enable Jinja's template auto-reload (useful in dev). We keep
        this False by default to avoid filesystem checks in hot paths.

    Notes
    -----
    - We intentionally keep Jinja's default undefined behavior (NOT StrictUndefined)
      to preserve current outputs that may omit some keys.
    - If you want strict rendering in the future, wire `undefined=StrictUndefined`
      into the Environment here (see TODO).
    """

    # TODO: Consider exposing a "strict" mode that uses StrictUndefined, but this
    # would be a behavioral change. Keep non-strict to avoid breaking callers.

    def __init__(
        self,
        template_dir: Optional[os.PathLike] = None,
        *,
        cache_templates: bool = True,
        auto_reload: bool = False,
    ) -> None:
        # Resolve the base prompts directory:
        env_dir = os.getenv("SAXOFLOW_PROMPT_DIR")
        if template_dir is not None:
            base_dir = Path(template_dir)
        elif env_dir:
            base_dir = Path(env_dir)
        else:
            # <repo>/saxoflow_agenticai/core/prompt_manager.py -> <repo>/prompts
            base_dir = Path(__file__).resolve().parents[1] / "prompts"

        self.template_dir: Path = base_dir
        self.cache_templates: bool = bool(cache_templates)

        # It is OK if directory does not exist yet; Jinja will raise on access.
        self.env: Environment = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            auto_reload=auto_reload,
        )

        # Local cache (optional) to avoid repeated loader lookups/parse
        self._cache: Dict[str, Any] = {}

        logger.debug(
            "PromptManager initialized (dir=%s, cache=%s, autoreload=%s)",
            self.template_dir,
            self.cache_templates,
            auto_reload,
        )

    # -----------------
    # Public operations
    # -----------------

    def render(self, template_file: str, context: Mapping[str, Any]) -> str:
        """
        Render the specified template with the provided context.

        Parameters
        ----------
        template_file : str
            Filename (relative to `template_dir`) of the template to render.
        context : Mapping[str, Any]
            Variables available to the template.

        Returns
        -------
        str
            The rendered text.

        Raises
        ------
        FileNotFoundError
            If the template cannot be located within `template_dir`.
        PromptRenderError
            If Jinja2 fails to parse or render the template for any other reason
            (e.g., syntax errors, runtime exceptions within template code).
        """
        try:
            template = self._get_template(template_file)
            rendered = template.render(dict(context))  # make sure it's a dict copy
            return rendered
        except TemplateNotFound as exc:
            raise FileNotFoundError(
                f"Prompt template '{template_file}' not found in '{self.template_dir}'."
            ) from exc
        except TemplateSyntaxError as exc:
            raise PromptRenderError(
                f"Syntax error in template '{template_file}' at line {exc.lineno}: {exc.message}"
            ) from exc
        except Exception as exc:
            # Catch-all for Jinja runtime errors (filters, undefineds, etc.)
            raise PromptRenderError(
                f"Failed to render template '{template_file}': {exc}"
            ) from exc

    # ---------------
    # Helper methods
    # ---------------

    def _get_template(self, template_file: str):
        """
        Retrieve a compiled Jinja2 template (from cache if enabled).

        Parameters
        ----------
        template_file : str
            Filename relative to `template_dir`.

        Returns
        -------
        jinja2.Template
            Compiled template object.

        Raises
        ------
        TemplateNotFound
            If the file cannot be located by the loader.
        TemplateSyntaxError
            If the template has syntax issues.
        """
        if self.cache_templates and template_file in self._cache:
            return self._cache[template_file]

        template = self.env.get_template(template_file)
        if self.cache_templates:
            self._cache[template_file] = template
        return template

    # ---------------------------------------------
    # Optional utilities (kept minimal and additive)
    # ---------------------------------------------

    def get_template_path(self, template_file: str) -> Path:
        """
        Compute the on-disk path for a given template name.

        This is useful for debugging/logging or test assertions.

        Parameters
        ----------
        template_file : str
            Template filename relative to `template_dir`.

        Returns
        -------
        Path
            The expected full path. Note: may not exist if using a multi-loader.
        """
        return (self.template_dir / template_file).resolve()

    # The methods below are intentionally commented out to keep the runtime
    # surface minimal and avoid introducing new behavior without need.
    #
    # def register_filter(self, name: str, func: Callable) -> None:
    #     """
    #     Register a custom Jinja2 filter at runtime.
    #     Kept as a reference for future templating needs (formatters, etc.).
    #     """
    #     self.env.filters[name] = func
    #
    # def register_global(self, name: str, value: Any) -> None:
    #     """
    #     Register a global variable available to all templates.
    #     """
    #     self.env.globals[name] = value
