param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8791
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# Pyodide mounts the current Windows drive. Keep uv's probe scripts and
# managed Pyodide runtime on the same drive as the project.
$env:UV_CACHE_DIR = Join-Path $ProjectRoot ".uv-cache"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $ProjectRoot ".uv-python"

Push-Location $ProjectRoot
try {
    python scripts/build_worker_bundle.py
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    python -m uv tool run --from uv uv run pywrangler dev --port $Port
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
