<#
.SYNOPSIS
    Bundles JobLookup so someone else can run it.

.DESCRIPTION
    Produces dist\joblookup-<version>\ and optionally a zip of it. The recipient
    extracts it and double-clicks "Start JobLookup.cmd" - nothing else.

    Everything the app opens at runtime is verified to have arrived before the
    bundle is declared good: the whole Python package, the web UI, the database
    schema, the portal selector files, the VS Code bridge and the launcher. The
    check walks the source tree rather than a hand-written list, so adding a
    screen or a portal cannot silently be left out of the next bundle.

    Deliberately excluded, so you never hand someone your own data:

      workspace\          your CVs, postings, scores and applications
      config\local.yaml   your provider, model and tuning choices
      .venv\              not relocatable; absolute paths are baked into it

    API keys are never in the bundle either, because they are never in a file
    the bundle would reach.

.PARAMETER Zip
    Also produce dist\joblookup-<version>.zip.

.PARAMETER Offline
    Bundle the Python packages as wheels so the recipient's machine never has to
    reach a package feed. Only useful when everyone runs the same Python minor
    version, because binary wheels are built per version.
#>
[CmdletBinding()]
param(
    [switch]$Zip,
    [switch]$Offline
)

# Windows PowerShell 5.1, ASCII only. See the note at the top of run.ps1.
$ErrorActionPreference = 'Stop'
$AppRoot = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
Set-Location $AppRoot

$version = (Select-String -Path (Join-Path $AppRoot 'joblookup\__init__.py') -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$distRoot = Join-Path $AppRoot 'dist'
$target = Join-Path $distRoot "joblookup-$version"

Write-Host "`n==> Packaging JobLookup $version" -ForegroundColor Cyan

if (Test-Path $target) { Remove-Item -Recurse -Force $target }
New-Item -ItemType Directory -Force -Path $target | Out-Null

# Directories are mirrored whole and then pruned. Copy-Item's -Exclude is
# unreliable underneath -Recurse on 5.1, so the prune is its own explicit pass.
$include = @(
    'joblookup',            # the application, including web/, db/*.sql and the portal YAML
    'vscode-bridge',        # the Copilot bridge extension
    'scripts',              # run.ps1, install-bridge.ps1, this script
    'tests',                # pyproject points pytest here; without it the suite cannot run
    'config\default.yaml',  # local.yaml is the recipient's own and is never shipped
    'pyproject.toml',
    'README.md',
    '.gitignore',           # stops a recipient committing their own CVs if they git init
    'Start JobLookup.cmd'
)

$prune = @('__pycache__', '.pytest_cache', '.ruff_cache', '*.egg-info', 'node_modules')

foreach ($item in $include) {
    $source = Join-Path $AppRoot $item
    if (-not (Test-Path $source)) {
        Write-Host "    ! $item is missing from the source tree" -ForegroundColor Yellow
        continue
    }
    $destination = Join-Path $target $item
    New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
    Copy-Item $source $destination -Recurse -Force
    Write-Host "    + $item" -ForegroundColor DarkGray
}

foreach ($pattern in $prune) {
    Get-ChildItem $target -Recurse -Force -Filter $pattern -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue }
}
Get-ChildItem $target -Recurse -Force -Include '*.pyc', '*.pyo' -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

# --- verification ------------------------------------------------------------
# Every file under these roots must have arrived. A bundle that starts and then
# 404s on its own stylesheet is worse than no bundle at all.
$mirrored = @('joblookup', 'vscode-bridge', 'scripts', 'tests')
$skip = '\\(__pycache__|\.pytest_cache|\.ruff_cache|node_modules)\\|\.pyc$'

$missing = @()
foreach ($root in $mirrored) {
    $sourceRoot = Join-Path $AppRoot $root
    if (-not (Test-Path $sourceRoot)) { continue }
    foreach ($file in (Get-ChildItem $sourceRoot -Recurse -File -Force)) {
        if ($file.FullName -match $skip) { continue }
        $relative = $file.FullName.Substring($AppRoot.Length).TrimStart('\')
        if (-not (Test-Path (Join-Path $target $relative))) { $missing += $relative }
    }
}
foreach ($file in @('config\default.yaml', 'pyproject.toml', 'README.md', 'Start JobLookup.cmd')) {
    if (-not (Test-Path (Join-Path $target $file))) { $missing += $file }
}

if ($missing.Count -gt 0) {
    Write-Host "`n  The bundle is incomplete. These files did not arrive:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    throw 'Packaging failed verification.'
}

foreach ($leaked in @('workspace', 'config\local.yaml', '.venv')) {
    if (Test-Path (Join-Path $target $leaked)) {
        throw "$leaked was copied into the bundle. It contains your own data and must not ship."
    }
}

$fileCount = (Get-ChildItem $target -Recurse -File -Force).Count
Write-Host "    verified $fileCount file(s)" -ForegroundColor DarkGray

# --- optional offline wheels -------------------------------------------------
if ($Offline) {
    Write-Host "`n==> Downloading wheels" -ForegroundColor Cyan
    $wheels = Join-Path $target 'vendor\wheels'
    New-Item -ItemType Directory -Force -Path $wheels | Out-Null
    $python = Join-Path $AppRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $python)) { $python = 'python' }
    & $python -m pip wheel '.[fuzzy,secrets,docs,schedule]' -w $wheels --quiet
    Write-Host "    bundled $((Get-ChildItem $wheels).Count) wheel(s)" -ForegroundColor DarkGray
    Write-Host '    These only work on the same Python minor version you built them with.' -ForegroundColor Yellow
}

@"
JobLookup $version

  1. Extract this folder somewhere you can write to.
  2. Double-click "Start JobLookup.cmd".

The first run sets everything up: a private Python environment inside this
folder, the packages it needs, and the GitHub Copilot bridge for VS Code. It
then opens a browser. Later runs start in a couple of seconds.

If VS Code was already open when you first ran it, reload it once:
press Ctrl+Shift+P and run "Developer: Reload Window".

If Windows says the file is blocked because it came from another computer:
right-click "Start JobLookup.cmd", choose Properties, tick Unblock, press OK.

You need a GitHub Copilot subscription, or a local Ollama server. No paid API
key is required either way. Nothing you do here leaves your machine except the
requests to the job boards and to the model you choose.
"@ | Set-Content -Path (Join-Path $target 'SETUP.txt') -Encoding ASCII

if ($Zip) {
    $archive = "$target.zip"
    if (Test-Path $archive) { Remove-Item -Force $archive }
    # The folder itself, not its contents, so extracting produces one tidy folder.
    Compress-Archive -Path $target -DestinationPath $archive
    $size = [math]::Round((Get-Item $archive).Length / 1MB, 2)
    Write-Host "`n    dist\joblookup-$version.zip  ($size MB)" -ForegroundColor Green
} else {
    Write-Host "`n    $target" -ForegroundColor Green
}
Write-Host ''
