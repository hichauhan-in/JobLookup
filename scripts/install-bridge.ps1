<#
.SYNOPSIS
    Installs (or removes) the JobLookup Bridge VS Code extension.

.DESCRIPTION
    The bridge is plain JavaScript with no build step, so it does not need to be
    packaged into a .vsix - copying it into VS Code's extensions folder is
    enough, and that needs neither the `code` CLI nor admin rights.

    Normally you do not run this yourself: the launcher calls it. It is kept as a
    separate script so it can be re-run, and so uninstalling is obvious.

.PARAMETER Quiet
    Print nothing unless something changed or went wrong.

.PARAMETER Uninstall
    Remove a previously installed copy.

.PARAMETER Insiders
    Target VS Code Insiders instead of stable.
#>
[CmdletBinding()]
param(
    [switch]$Quiet,
    [switch]$Uninstall,
    [switch]$Insiders
)

# Windows PowerShell 5.1, ASCII only. See the note at the top of run.ps1.
$ErrorActionPreference = 'Stop'
$AppRoot = Split-Path -Parent $PSScriptRoot

$extensionId = 'joblookup.joblookup-bridge'
$source = Join-Path $AppRoot 'vscode-bridge'
$root = Join-Path $HOME $(if ($Insiders) { '.vscode-insiders' } else { '.vscode' })
$extensionsDir = Join-Path $root 'extensions'

function Say($message, $colour = 'Gray') { if (-not $Quiet) { Write-Host $message -ForegroundColor $colour } }

# VS Code creates this on first launch. No folder means VS Code has never run
# here, so there is nothing to install into.
if (-not (Test-Path $extensionsDir)) {
    Say '  VS Code was not found, so the Copilot bridge was not installed.' Yellow
    Say '  You can still use the Copilot CLI, or a local Ollama server.' DarkGray
    return [pscustomobject]@{ Status = 'no-vscode'; Path = $null }
}

if (-not (Test-Path $source)) {
    throw "The vscode-bridge folder is missing from $AppRoot."
}

$manifest = Get-Content (Join-Path $source 'package.json') -Raw | ConvertFrom-Json
$target = Join-Path $extensionsDir "$extensionId-$($manifest.version)"

if ($Uninstall) {
    $removed = 0
    Get-ChildItem $extensionsDir -Directory -Filter "$extensionId-*" -ErrorAction SilentlyContinue |
        ForEach-Object {
            Remove-Item -Recurse -Force $_.FullName
            Say "  Removed $($_.Name)" DarkGray
            $removed++
        }
    if ($removed -eq 0) { Say '  Nothing to remove.' Yellow }
    else { Say "`n  Reload VS Code to finish removing it.`n" Green }
    return [pscustomobject]@{ Status = 'uninstalled'; Path = $null }
}

# Already current: leave it alone so a normal start stays fast and silent.
$installed = Get-ChildItem $extensionsDir -Directory -Filter "$extensionId-*" -ErrorAction SilentlyContinue
if ($installed.Name -contains (Split-Path $target -Leaf)) {
    $stamp = Join-Path $target 'extension.js'
    $sourceStamp = Join-Path $source 'extension.js'
    if ((Test-Path $stamp) -and
        (Get-Item $stamp).LastWriteTimeUtc -ge (Get-Item $sourceStamp).LastWriteTimeUtc) {
        Say "  Copilot bridge $($manifest.version) is already installed." DarkGray
        return [pscustomobject]@{ Status = 'current'; Path = $target }
    }
}

# Clear out older versions so VS Code does not load two copies.
$installed | ForEach-Object { Remove-Item -Recurse -Force $_.FullName }

New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -Path (Join-Path $source '*') -Destination $target -Recurse -Force -Exclude 'node_modules'

# Installing is the one thing worth reporting even in quiet mode.
Write-Host "    Installed the Copilot bridge $($manifest.version) into VS Code." -ForegroundColor Green
return [pscustomobject]@{ Status = 'installed'; Path = $target }
