# cool_cli/completers.py
"""
Prompt-toolkit completer utilities.

This module provides a hybrid completer that offers fuzzy command completion
until the first space, and file-system path completion thereafter.

Public API
----------
- HybridShellCompleter: prompt-toolkit Completer that combines fuzzy command
  completion and path completion with user-friendly behavior.

Notes
-----
- Behavior is intentionally preserved from the original implementation.
- The class guards against unexpected exceptions coming from underlying
  completers so the shell won't crash during interactive completion.
- Python 3.9+ compatible.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator

from prompt_toolkit.completion import (
    Completer,
    Completion,
    FuzzyWordCompleter,
    PathCompleter,
)
from prompt_toolkit.document import Document

__all__ = ["HybridShellCompleter"]


class HybridShellCompleter(Completer):
    """Command+path completer: commands before the first space, paths after.

    Parameters
    ----------
    commands : Iterable[str]
        Collection of available command names (first-token suggestions).

    Examples
    --------
    >>> comp = HybridShellCompleter(commands=["help", "quit", "ls"])
    >>> # In a prompt-toolkit session:
    >>> # session = PromptSession(completer=comp)

    Design
    ------
    - Before the first whitespace, we delegate to `FuzzyWordCompleter`.
    - After the first whitespace, we delegate to `PathCompleter` with
      `expanduser=True` so `~` is resolved to the home directory.
    - Any errors during completion are swallowed to keep the TUI responsive.
    """

    __slots__ = ("command_completer", "path_completer")

    def __init__(self, commands: Iterable[str]) -> None:
        # Fuzzy list completer for the very first token
        # NOTE: We materialize the iterable to avoid late changes to the source.
        self.command_completer = FuzzyWordCompleter(list(commands))
        # Path completion for arguments (files/dirs), with ~ expansion
        # TODO(decide-future): consider enable "only_directories" for certain commands.
        self.path_completer = PathCompleter(expanduser=True)

    # prompt-toolkit's Completer interface is not strictly typed; we keep the
    # signature and ignore override typing to remain compatible across versions.
    def get_completions(  # type: ignore[override]
        self, document: Document, complete_event: Any
    ) -> Iterator[Completion]:
        """Yield completions based on cursor position relative to first space.

        Parameters
        ----------
        document : prompt_toolkit.document.Document
            The current buffer document.
        complete_event : Any
            Event object from prompt-toolkit (unused here, just forwarded).

        Yields
        ------
        prompt_toolkit.completion.Completion
            Completion items either for commands or for paths.
        """
        buf = document.text_before_cursor
        first_space = buf.find(" ")

        # 1) Command-name completion (before the first space)
        if first_space == -1 or document.cursor_position <= first_space:
            # Delegate to the fuzzy command completer
            try:
                yield from self.command_completer.get_completions(document, complete_event)
            except Exception:  # noqa: BLE001
                # Defensive: if the inner completer explodes, we don't break the shell.
                return
            return

        # 2) Argument/path completion (after the first space)
        fragment = buf[first_space + 1 :]
        frag_doc = Document(text=fragment, cursor_position=len(fragment))

        try:
            for c in self.path_completer.get_completions(frag_doc, complete_event):
                # Show the full suggestion (existing fragment + proposed suffix)
                full_text = fragment + c.text
                yield Completion(
                    text=full_text,
                    start_position=-len(fragment),  # replace exactly the argument fragment
                    display=full_text,
                    display_meta=c.display_meta,
                )
        except Exception:  # noqa: BLE001
            # Defensive: swallow unexpected completion errors
            return
