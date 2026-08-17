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

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `joblookupBridge.port` | `8771` | Listening port. `0` picks a free one. |
| `joblookupBridge.modelFamily` | *(empty)* | Force a model family. Empty picks a fast, inexpensive one. |
| `joblookupBridge.autoStart` | `true` | Start when VS Code opens. |

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Availability, consent state, visible models |
| `POST` | `/v1/chat/completions` | OpenAI-shaped chat request |
