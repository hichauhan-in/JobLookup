"""Rewriting a CV for one posting, without ever inventing experience."""

from __future__ import annotations

from joblookup.tailor.docx_builder import DocxUnavailable, available_templates, build
from joblookup.tailor.generate import TailorResult, prep_markdown, tailor, to_markdown
from joblookup.tailor.style_guard import GuardReport, clean, clean_document

__all__ = [
    "DocxUnavailable",
    "GuardReport",
    "TailorResult",
    "available_templates",
    "build",
    "clean",
    "clean_document",
    "prep_markdown",
    "tailor",
    "to_markdown",
]
