"""Writing the tailored CV out as a Word document.

Deliberately plain: one clean single-column layout that survives an applicant
tracking system's text extraction. Fancy templates with tables and text boxes
look better on screen and parse badly, which is the wrong trade for a document
whose first reader is usually software.

Drop your own ``.docx`` into ``templates/`` and name it in ``tailor.template`` if
you would rather keep your existing layout; its styles are then used instead of
the built-in ones.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from joblookup.config import Settings
from joblookup.paths import ensure_dir, package_dir

TEMPLATES_DIR = package_dir() / "tailor" / "templates"


class DocxUnavailable(RuntimeError):
    """python-docx is missing, which should not happen in a normal install."""


def build(
    content: dict[str, Any],
    profile: dict[str, Any],
    settings: Settings,
    destination: Path,
) -> Path:
    try:
        import docx
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt
    except ImportError as exc:  # pragma: no cover
        raise DocxUnavailable(
            "python-docx is not installed, so DOCX export is unavailable. "
            "Markdown export still works."
        ) from exc

    template = _template_path(settings)
    document = docx.Document(str(template)) if template else docx.Document()
    if template:
        # A template is used for its styles, not its content.
        for paragraph in list(document.paragraphs):
            paragraph._element.getparent().remove(paragraph._element)

    _configure(document, Pt)

    name = str(profile.get("full_name") or "").strip()
    if name:
        heading = document.add_paragraph(name)
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = heading.runs[0]
        run.bold = True
        run.font.size = Pt(20)

    if content.get("headline"):
        line = document.add_paragraph(content["headline"])
        line.alignment = WD_ALIGN_PARAGRAPH.CENTER
        line.runs[0].italic = True

    contact = [
        str(profile.get(key) or "").strip()
        for key in ("location", "email", "phone")
        if str(profile.get(key) or "").strip()
    ]
    contact += [str(link) for link in (profile.get("links") or [])[:3]]
    if contact:
        line = document.add_paragraph(" | ".join(contact))
        line.alignment = WD_ALIGN_PARAGRAPH.CENTER
        line.runs[0].font.size = Pt(9)

    if content.get("summary"):
        _section(document, "Summary", Pt)
        document.add_paragraph(content["summary"])

    if content.get("highlighted_skills"):
        _section(document, "Skills", Pt)
        document.add_paragraph(", ".join(content["highlighted_skills"]))

    if content.get("roles"):
        _section(document, "Experience", Pt)
        for role in content["roles"]:
            title = role.get("title", "")
            if role.get("company"):
                title += f", {role['company']}"
            dates = " - ".join(part for part in (role.get("start"), role.get("end")) if part)

            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_before = Pt(8)
            run = paragraph.add_run(title)
            run.bold = True
            if dates:
                tail = paragraph.add_run(f"    {dates}")
                tail.italic = True
                tail.font.size = Pt(9)

            for bullet in role.get("bullets") or []:
                document.add_paragraph(bullet, style="List Bullet")

    if content.get("upskilling") and settings.tailor.include_upskilling_section:
        _section(document, settings.tailor.upskilling_heading, Pt)
        document.add_paragraph(", ".join(content["upskilling"]))

    if profile.get("education"):
        _section(document, "Education", Pt)
        for entry in profile["education"]:
            parts = [entry.get("degree", ""), entry.get("institution", ""), entry.get("year", "")]
            document.add_paragraph(", ".join(part for part in parts if part), style="List Bullet")

    if profile.get("certifications"):
        _section(document, "Certifications", Pt)
        document.add_paragraph(", ".join(str(item) for item in profile["certifications"]))

    ensure_dir(destination.parent)
    document.save(str(destination))
    return destination


def _configure(document: Any, Pt: Any) -> None:
    style = document.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    style.paragraph_format.space_after = Pt(4)


def _section(document: Any, title: str, Pt: Any) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(12)
    run = paragraph.add_run(title.upper())
    run.bold = True
    run.font.size = Pt(11)


def _template_path(settings: Settings) -> Path | None:
    name = (settings.tailor.template or "").strip()
    if not name:
        return None
    candidate = Path(name)
    if not candidate.is_absolute():
        candidate = TEMPLATES_DIR / name
    return candidate if candidate.is_file() else None


def available_templates() -> list[str]:
    if not TEMPLATES_DIR.is_dir():
        return []
    return sorted(path.name for path in TEMPLATES_DIR.glob("*.docx"))
