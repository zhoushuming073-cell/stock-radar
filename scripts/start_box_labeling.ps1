param(
    [int]$Port = 8124,
    [string]$ResearchRoot = '',
    [string]$CodeRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
)

$ErrorActionPreference='Stop'
if (!$ResearchRoot) {
    $ResearchRoot = if (Test-Path -LiteralPath (Join-Path $CodeRoot 'data\shape-research')) { $CodeRoot }
                    else { Join-Path (Split-Path $CodeRoot -Parent) 'stock-radar' }
}
$env:PYTHONPATH=Join-Path $CodeRoot 'src'
$env:STOCK_RADAR_RESEARCH_ROOT=$ResearchRoot
$env:STOCK_RADAR_BOX_DATA_ROOT=Join-Path $CodeRoot 'data\box-label-v1-2m-1y-4y'
$env:LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED='true'
$env:LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT=Join-Path $ResearchRoot 'data'
$env:LABEL_STUDIO_BASE_DATA_DIR=Join-Path $ResearchRoot 'data\vision-research\label-studio'
$env:LABEL_STUDIO_HOST="http://localhost:$Port"
$env:LABEL_STUDIO_DISABLE_SIGNUP_WITHOUT_LINK='true'
$env:LABEL_STUDIO_COLLECT_ANALYTICS='false'
$env:LATEST_VERSION_CHECK='false'
$env:SENTRY_DSN=''
$env:FRONTEND_SENTRY_DSN=''
$Python=Join-Path $ResearchRoot '.venv-label-studio\Scripts\python.exe'
if (!(Test-Path -LiteralPath $Python)) { throw 'Existing Label Studio environment is missing.' }
if (!(Test-Path -LiteralPath (Join-Path $env:STOCK_RADAR_BOX_DATA_ROOT 'manifest.json'))) { throw 'Private task manifest is missing.' }
& $Python (Join-Path $PSScriptRoot 'start_label_studio_wsgi.py') start --host "http://localhost:$Port" --internal-host 127.0.0.1 --port $Port --no-browser
