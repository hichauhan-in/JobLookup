"""Explicit, validated local workspace export and restore."""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from joblookup.config import Settings
from joblookup.server.jobs import manager
from joblookup.services import backups


def build_router(settings_getter: Callable[[], Settings]) -> APIRouter:
    router = APIRouter(prefix="/api/backups")

    def ready() -> Settings:
        settings = settings_getter()
        if settings.server.multi_user:
            raise HTTPException(400, "Portable backups are available only in local mode.")
        if manager.active():
            raise HTTPException(
                409, "Wait for active tasks to finish before backing up or restoring."
            )
        return settings

    @router.get("/export")
    def export() -> Response:
        settings = ready()
        try:
            data = backups.export_workspace(settings.paths.workspace_dir)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return Response(
            data,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="joblookup-workspace.zip"'},
        )

    @router.post("/preview")
    def preview(file: UploadFile = File(...)) -> dict[str, Any]:
        ready()
        try:
            return backups.preview_workspace(file.file.read(backups.MAX_ARCHIVE + 1))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/restore")
    def restore(
        file: UploadFile = File(...), confirmation: str = Form(...), sha256: str = Form(...)
    ) -> dict[str, Any]:
        import hashlib

        settings = ready()
        if confirmation != "RESTORE":
            raise HTTPException(
                400, "Type RESTORE to replace this workspace with the previewed backup."
            )
        data = file.file.read(backups.MAX_ARCHIVE + 1)
        if hashlib.sha256(data).hexdigest() != sha256:
            raise HTTPException(
                409, "This file differs from the previewed backup. Preview it again."
            )
        try:
            return backups.restore_workspace(data, settings.paths.workspace_dir)
        except (ValueError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc

    return router
