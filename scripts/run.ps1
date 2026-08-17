<#
.SYNOPSIS
    Starts JobLookup. This is the only thing you need to run.

.DESCRIPTION
    Does whatever setup is outstanding, then starts the app and opens a browser.
    On a machine that is already set up it skips straight to starting, which
    takes a couple of seconds.

    First run only:
      * finds Python, offering to install it if it is missing
      * creates a private environment in .venv and installs the packages
      * installs the Copilot bridge into VS Code
      * adds a Start Menu shortcut

    Nothing is installed system-wide and nothing is added to PATH. Deleting this
    folder removes JobLookup.

.PARAMETER Port
    Override the port (default 8770).

.PARAMETER NoBrowser
    Do not open a browser.

.PARAMETER NoBridge
    Do not install or update the VS Code Copilot bridge.

.PARAMETER WithPortals
    Also install Playwright, for logged-in portal scraping. Not needed unless
    you intend to enable a Tier B portal, and it is a large download.

.PARAMETER Reinstall
    Rebuild the Python environment from scratch.

.PARAMETER Doctor
    Run the health checks and exit without starting the server.
#>
[CmdletBinding()]
param(
    [int]$Port = 0,
    [switch]$NoBrowser,
    [switch]$NoBridge,
    [switch]$WithPortals,
    [switch]$Reinstall,
    [switch]$Doctor
)

# These scripts must run under Windows PowerShell 5.1, which is what every
# Windows machine has and what "Start JobLookup.cmd" invokes. No PowerShell 7
# syntax, and ASCII only: 5.1 reads a UTF-8 file without a BOM as the legacy
# code page, which would corrupt any non-ASCII character it prints.

$ErrorActionPreference = 'Stop'
$AppRoot = Split-Path -Parent $PSScriptRoot
Set-Location -Path $AppRoot

$VenvDir = Join-Path $AppRoot '.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$FirstRunMarker = Join-Path $VenvDir '.joblookup-configured'

function Write-Step($message) { Write-Host "`n==> $message" -ForegroundColor Cyan }
function Write-Note($message) { Write-Host "    $message" -ForegroundColor DarkGray }
function Write-Warn($message) { Write-Host "    $message" -ForegroundColor Yellow }

# --- Python ------------------------------------------------------------------
function Find-Python {
    # The `py` launcher points at a real CPython install. A bare `python` on PATH
    # is often an MSys2 or Store shim whose venv layout differs, so it is a last
    # resort. A Store Python also cannot see FTS5 reliably, which lexical recall
    # depends on.
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($version in '3.13', '3.12', '3.11', '3.10', '3') {
            $candidates += , @('py', "-$version")
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) { $candidates += , @('python') }

    # A winget install does not update PATH for an already-running shell, so look
    # where it lands as well.
    foreach ($dir in (Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Directory -ErrorAction SilentlyContinue |
                      Sort-Object Name -Descending)) {
        $exe = Join-Path $dir.FullName 'python.exe'
        if (Test-Path $exe) { $candidates += , @($exe) }
    }

    foreach ($candidate in $candidates) {
        try {
            $exe = $candidate[0]
            $probeArgs = @($candidate[1..($candidate.Length - 1)]) +
                         @('-c', 'import sys; print(sys.version_info[0], sys.version_info[1])')
            $output = & $exe @probeArgs 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $output) { continue }
            $parts = ($output -split '\s+')
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 10) { return $candidate }
        } catch { continue }
    }
    return $null
}

function Install-Python {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { return $null }

    Write-Note 'Installing Python for you (no admin rights needed)...'
    # User scope keeps this out of Program Files, so there is no elevation prompt.
    winget install --id Python.Python.3.12 -e --scope user --silent `
        --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Note 'A per-user install was not possible; trying the default scope...'
        winget install --id Python.Python.3.12 -e --silent `
            --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null
    }
    return Find-Python
}

# --- setup -------------------------------------------------------------------
if ($Reinstall -and (Test-Path $VenvDir)) {
    Write-Step 'Removing the existing environment'
    Remove-Item -Recurse -Force $VenvDir
}

$isFirstRun = -not (Test-Path $FirstRunMarker)

if (-not (Test-Path $VenvPython)) {
    Write-Step 'Setting up Python'
    $python = Find-Python
    if (-not $python) { $python = Install-Python }

    if (-not $python) {
        Write-Host @'

  Python 3.10 or newer is required, and it could not be installed automatically.

  Install it with:

      winget install --id Python.Python.3.12 -e

  or from https://www.python.org/downloads/ (tick "Add python.exe to PATH").
  Then run this again.

'@ -ForegroundColor Yellow
        Read-Host 'Press Enter to close'
        exit 1
    }

    $exe = $python[0]
    $prefix = @($python[1..($python.Length - 1)])
    Write-Note "Using $exe $($prefix -join ' ')"
    & $exe @prefix -m venv $VenvDir
    if (-not (Test-Path $VenvPython)) {
        Write-Host "  Could not create a virtual environment at $VenvDir." -ForegroundColor Red
        Read-Host 'Press Enter to close'
        exit 1
    }
}

# Reinstall only when the dependency set may have changed. pip is fast when it
# has nothing to do, but skipping it entirely makes startup noticeably snappier.
$stamp = Join-Path $VenvDir '.joblookup-install-stamp'
$projectFile = Join-Path $AppRoot 'pyproject.toml'
$needsInstall = -not (Test-Path $stamp) -or
                (Get-Item $projectFile).LastWriteTimeUtc -gt (Get-Item $stamp).LastWriteTimeUtc

if ($needsInstall) {
    Write-Step 'Installing Python packages'
    Write-Note 'This only happens once, and takes a minute or two.'
    & $VenvPython -m pip install --upgrade pip --quiet --disable-pip-version-check

    # A bundled wheel set means the machine never has to reach a package feed.
    $wheels = Join-Path $AppRoot 'vendor\wheels'
    $offlineArgs = if (Test-Path $wheels) { @('--no-index', '--find-links', $wheels) } else { @() }

    # fuzzy and secrets are small and make a real difference to duplicate
    # detection and to where API keys are kept, so they are part of a normal
    # install. Everything heavy stays out.
    $target = if ($WithPortals) { '.[fuzzy,secrets,docs,schedule,portals]' } else { '.[fuzzy,secrets,docs,schedule]' }
    & $VenvPython -m pip install -e $target --quiet --disable-pip-version-check @offlineArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Warn 'The optional extras could not be installed. Trying the core packages only.'
        & $VenvPython -m pip install -e . --quiet --disable-pip-version-check @offlineArgs
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n  Installing the Python packages failed. See the output above." -ForegroundColor Red
        Read-Host 'Press Enter to close'
        exit 1
    }
    New-Item -ItemType File -Path $stamp -Force | Out-Null
    Write-Note 'Done.'
}

if ($WithPortals) {
    Write-Step 'Downloading Chromium for portal scraping'
    & $VenvPython -m playwright install chromium
    if ($LASTEXITCODE -ne 0) {
        Write-Warn 'Chromium could not be downloaded. Portal scraping will stay unavailable.'
    }
}

# --- Copilot bridge ----------------------------------------------------------
if (-not $NoBridge) {
    Write-Step 'Checking the GitHub Copilot bridge for VS Code'
    try {
        $bridge = & (Join-Path $PSScriptRoot 'install-bridge.ps1') -Quiet
        if ($bridge.Status -eq 'installed') {
            Write-Warn 'If VS Code is already open, reload it: Ctrl+Shift+P, "Developer: Reload Window".'
        }
    } catch {
        Write-Warn "The bridge could not be installed: $_"
    }
}

# --- Start Menu shortcut -----------------------------------------------------
if ($isFirstRun) {
    try {
        $startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
        $shortcut = Join-Path $startMenu 'JobLookup.lnk'
        if (-not (Test-Path $shortcut)) {
            $shell = New-Object -ComObject WScript.Shell
            $link = $shell.CreateShortcut($shortcut)
            $link.TargetPath = Join-Path $AppRoot 'Start JobLookup.cmd'
            $link.WorkingDirectory = $AppRoot
            $link.Description = 'A local-first job finder'
            $link.Save()
            Write-Note 'Added a JobLookup shortcut to the Start Menu.'
        }
    } catch {
        Write-Note 'The Start Menu shortcut could not be created. Not a problem.'
    }
    New-Item -ItemType File -Path $FirstRunMarker -Force | Out-Null
}

# --- go ----------------------------------------------------------------------
if ($Doctor) {
    & $VenvPython -m joblookup doctor
    exit $LASTEXITCODE
}

$runArgs = @('-m', 'joblookup', 'serve')
if ($Port -gt 0) { $runArgs += @('--port', "$Port") }
if ($NoBrowser) { $runArgs += '--no-browser' }

Write-Step 'Starting JobLookup'
& $VenvPython @runArgs
exit $LASTEXITCODE
