"""Where jobs come from.

Nothing here re-exports a name that would shadow a submodule — in particular
``normalize``, so ``from joblookup.sources import normalize`` gives you the
module rather than the function inside it.
"""

from __future__ import annotations

from joblookup.sources.base import (
    ConfigField,
    FetchContext,
    SourceAdapter,
    SourceError,
)

__all__ = [
    "ConfigField",
    "FetchContext",
    "SourceAdapter",
    "SourceError",
]
