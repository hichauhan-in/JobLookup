"""Command line entry point: ``python -m joblookup``."""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser

from joblookup import __version__
from joblookup.config import load_settings


def _free_port(host: str, preferred: int) -> int:
    """Use the configured port, or the next free one rather than failing.

    A stale process holding the port is a two-minute detour for someone who just
    wants to look at their job matches.
    """
    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, candidate))
                return probe.getsockname()[1]
            except OSError:
                continue
    return preferred


def serve(args: argparse.Namespace) -> int:
    import uvicorn

    from joblookup.server import create_app

    settings = load_settings(args.config)
    if args.port:
        settings.server.port = args.port
    if args.host:
        settings.server.host = args.host

    port = _free_port(settings.server.host, settings.server.port)
    if port != settings.server.port:
        print(f"Port {settings.server.port} is in use; using {port} instead.")
        settings.server.port = port

    url = f"http://{settings.server.host}:{port}"
    app = create_app(settings)

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    print(f"\n  JobLookup is running at {url}\n  Press Ctrl+C to stop.\n")
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=settings.server.host,
            port=port,
            log_level=settings.logging.level.lower(),
            access_log=False,
        )
    )
    # Lets the Quit button in the sidebar stop this process. Built here rather
    # than in the app so an embedded or test instance simply has no way to.
    app.state.request_shutdown = lambda: setattr(server, "should_exit", True)
    server.run()
    return 0


def doctor_command(args: argparse.Namespace) -> int:
    import json

    from joblookup import doctor
    from joblookup.db import session as db
    from joblookup.sources import registry

    settings = load_settings(args.config)
    db.configure(settings.paths.workspace_dir)
    registry.sync_source_table()
    report = doctor.run_all(settings)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report["status"] != "failed" else 1

    symbols = {"ok": "  ok  ", "warning": " warn ", "failed": " FAIL "}
    print(f"\nJobLookup {report['version']} — {report['status']}\n")
    for check in report["checks"]:
        print(f"[{symbols.get(check['status'], '  ?   ')}] {check['label']}: {check['detail']}")
        if check["fix"]:
            print(f"          → {check['fix']}")
    print()
    return 0 if report["status"] != "failed" else 1


def install_bridge(args: argparse.Namespace) -> int:
    """Copy the VS Code extension into place without needing PowerShell."""
    import json
    import shutil

    from joblookup.llm.vscode_bridge import EXTENSION_ID
    from joblookup.paths import app_root

    source = app_root() / "vscode-bridge"
    if not source.is_dir():
        print(f"Could not find the bridge source at {source}.", file=sys.stderr)
        return 1

    from pathlib import Path

    manifest = json.loads((source / "package.json").read_text(encoding="utf-8"))
    installed = 0
    for root in (".vscode", ".vscode-insiders"):
        extensions = Path.home() / root / "extensions"
        if not extensions.is_dir():
            continue
        target = extensions / f"{EXTENSION_ID}-{manifest['version']}"
        if args.uninstall:
            shutil.rmtree(target, ignore_errors=True)
            print(f"Removed {target}")
        else:
            for previous in extensions.glob(f"{EXTENSION_ID}-*"):
                if previous.is_dir():
                    shutil.rmtree(previous)
            shutil.copytree(source, target)
            print(f"Installed to {target}")
        installed += 1

    if not installed:
        print("No VS Code installation was found under your home directory.", file=sys.stderr)
        return 1
    if not args.uninstall:
        print("\nNow reload VS Code (Ctrl+Shift+P → 'Developer: Reload Window') and run")
        print("'JobLookup Bridge: Authorise Copilot Access' once.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="joblookup", description="A local-first job finder.")
    parser.add_argument("--version", action="version", version=f"JobLookup {__version__}")
    parser.add_argument("--config", help="An extra YAML file layered on top of the defaults.")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("serve", help="Start the web app (default).")
    run.add_argument("--host")
    run.add_argument("--port", type=int)
    run.add_argument("--no-browser", action="store_true")
    run.set_defaults(func=serve)

    check = sub.add_parser("doctor", help="Check that everything is set up correctly.")
    check.add_argument("--json", action="store_true")
    check.set_defaults(func=doctor_command)

    bridge = sub.add_parser("install-bridge", help="Install the VS Code bridge extension.")
    bridge.add_argument("--uninstall", action="store_true")
    bridge.set_defaults(func=install_bridge)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args = parser.parse_args([*(argv or []), "serve"])
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
