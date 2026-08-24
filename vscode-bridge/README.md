# JobLookup Bridge

A local-only bridge that lets the JobLookup app on this machine use your GitHub
Copilot seat.

## What it does

Starts an HTTP server on `127.0.0.1` and forwards chat requests to VS Code's
[Language Model API](https://code.visualstudio.com/api/extension-guides/language-model)
(`vscode.lm`) — the same API every Copilot-powered extension uses. Quota, policy
and telemetry all behave exactly as they would for any other extension.

It does **not** reuse a Copilot token, call a private endpoint, or impersonate a
Copilot client.

## Installing

From the JobLookup folder:

```powershell
.\scripts\install-bridge.ps1
```

Then reload VS Code (<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> →
`Developer: Reload Window`) and run **JobLookup Bridge: Authorise Copilot
Access** once. VS Code only shows the consent dialog in response to a command you
invoked yourself, which is why that step cannot be automated.

To remove it: `.\scripts\install-bridge.ps1 -Uninstall`.

## Security

| Control | Why |
| --- | --- |
| Binds `127.0.0.1` only | Never reachable from the network |
| Per-session bearer token in `~/.joblookup/bridge.json`, mode 0600 | Another process cannot quietly spend your Copilot quota |
| Constant-time token comparison | The token cannot be guessed a byte at a time |
| Rejects any request carrying `Origin` or `Sec-Fetch-Site` | Blocks a malicious web page attempting DNS rebinding |
| 8 MB request body cap | Bounded memory |

The token is regenerated every time the extension starts, so the handshake file
is only valid while that VS Code window is open.

## When the port is busy

Two different situations look the same from the outside, so the extension tells
them apart:

* **Another VS Code window is hosting.** Normal, and nothing to fix. This window
  logs a line, stands down, and retries every 30 seconds so that closing the
  hosting window hands over rather than leaving you with nothing.
* **Something that is not the bridge has the port.** The extension takes a free
  port instead and records it in the handshake. JobLookup reads the port out of
  that file, so it does not have to be the usual one and no setting needs
  changing.

Only the window that wins an exclusive create of the handshake hosts, so two
windows can never both believe they are serving.

Neither case raises a dialog. An error dialog now means something the extension
genuinely cannot work around, and it comes with a **Show log** button.

## Several VS Code windows

Every open window loads this extension, but only one can hold the port. The
first to bind hosts the bridge and writes the handshake; the rest log a line and
stand down, retrying every 30 seconds so that closing the hosting window hands
over rather than leaving you with nothing.

The handshake records the process that wrote it, and only that process may
delete it. Without that rule, closing or reloading any other window removes the
handshake belonging to the window that is actually serving, and JobLookup stops
being able to authenticate even though the bridge is still running. The host
also re-checks the file every 10 seconds and puts it back if anything removed
it, so the system recovers on its own.

The status bar shows `$(broadcast) JobLookup` both when this window is hosting
and when another one is, because in both cases there is nothing to fix. Hover it
to see which.

If JobLookup reports that a bridge is listening but has not written its
handshake, an older build is still resident in a window. Reload that window:
<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> → **Developer: Reload Window**.

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `joblookupBridge.port` | `8771` | Preferred port. If something else has it, a free one is used automatically. `0` always picks a free one. |
| `joblookupBridge.modelFamily` | *(empty)* | Force a model family. Empty picks a fast, inexpensive one. |
| `joblookupBridge.autoStart` | `true` | Start when VS Code opens. |

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Availability, consent state, visible models |
| `POST` | `/v1/chat/completions` | OpenAI-shaped chat request |
