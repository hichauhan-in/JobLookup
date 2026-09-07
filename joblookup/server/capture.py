"""Preview and confirm explicit imports and availability checks."""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from joblookup.config import Settings
from joblookup.server.jobs import Job, manager
from joblookup.server.portals import PostingImport
from joblookup.services import capture
from joblookup.sources.base import SourceError


class PreviewBody(BaseModel):
    text: str = Field(default="", max_length=250_000)
    url: str = Field(default="", max_length=2048)
    fetch_url: bool = False


class CaptureBody(PostingImport):
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str = Field(default="", max_length=10)
    salary_period: str = Field(default="", max_length=10)


def build_router(settings_getter: Callable[[], Settings]) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/capture/extension")
    def extension(request: Request) -> Response:
        import io
        import json
        import zipfile
        from pathlib import Path

        folder = Path(__file__).resolve().parents[1] / "capture_extension"
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in ("manifest.json", "popup.html", "popup.css", "popup.js", "README.txt"):
                archive.write(folder / name, name)
            archive.writestr(
                "settings.json", json.dumps({"origin": str(request.base_url).rstrip("/")})
            )
        return Response(
            output.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="joblookup-capture.zip"'},
        )

    @router.post("/capture/preview")
    def preview(body: PreviewBody) -> dict[str, Any]:
        try:
            text, url = body.text, body.url
            if body.fetch_url:
                text, status, url = capture.fetch_page(body.url, settings_getter())
                if status in {404, 410}:
                    raise ValueError("The original page is no longer available.")
            return {"items": capture.preview(text, url)}
        except (SourceError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/capture/import")
    def import_posting(body: CaptureBody) -> dict[str, Any]:
        try:
            return capture.import_posting(body.model_dump())
        except (SourceError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/opportunities/{job_id}/check")
    def check(job_id: int) -> dict[str, Any]:
        from joblookup import store

        if not store.get_job(job_id):
            raise HTTPException(404, "This job no longer exists.")
        settings = settings_getter().model_copy(deep=True)

        def work(bus: Any, task: Job) -> dict[str, Any]:
            return capture.check_availability(job_id, settings)

        return {
            "task": manager.submit(
                "availability", work, label="Checking the public posting", single=False
            ).summary()
        }

    return router
