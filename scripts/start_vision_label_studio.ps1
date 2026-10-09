param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [switch]$Install,
    [string]$Python311,
    [int]$Port = 8123,
    [switch]$InstallOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$DataRoot = (Resolve-Path (Join-Path $ProjectRoot "data")).Path
$Venv = Join-Path $ProjectRoot ".venv-label-studio"
$Python = Join-Path $Venv "Scripts\python.exe"
$LabelStudio = Join-Path $Venv "Scripts\label-studio.exe"

if (-not (Test-Path $Python)) {
    if (-not $Install) {
        throw "Label Studio virtualenv not found. Re-run with -Install."
    }
    if (-not $Python311) {
        $Candidate = 'D:\QuantConnect-LEAN\runtime\python-package\tools\python.exe'
        if (Test-Path -LiteralPath $Candidate) { $Python311 = $Candidate }
        elseif (Get-Command py -ErrorAction SilentlyContinue) {
            $Python311 = (& py -3.11 -c 'import sys; print(sys.executable)').Trim()
        }
        else { throw 'Python 3.11 required for the separate Label Studio environment. Supply -Python311 with its actual path.' }
    }
    $Version = & $Python311 -c 'import sys; print("%s.%s" % sys.version_info[:2])'
    if ($LASTEXITCODE -ne 0 -or $Version -ne '3.11') { throw 'The selected Label Studio bootstrap must be Python 3.11.' }
    & $Python311 -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create Label Studio virtualenv.' }
}

if ($Install -or -not (Test-Path $LabelStudio)) {
    & $Python -m pip install "label-studio>=1.23,<2" "waitress>=3,<4" "whitenoise>=6,<7"
    if ($LASTEXITCODE -ne 0) { throw 'Label Studio installation failed.' }
}

$env:LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED = "true"
$env:LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT = $DataRoot
$env:LABEL_STUDIO_BASE_DATA_DIR = Join-Path $DataRoot 'vision-research\label-studio'
$env:LABEL_STUDIO_HOST = "http://localhost:$Port"
$env:LABEL_STUDIO_DISABLE_SIGNUP_WITHOUT_LINK = 'true'
$env:LABEL_STUDIO_COLLECT_ANALYTICS = 'false'
if ($InstallOnly) { return }
$LoginPath = Join-Path $env:LABEL_STUDIO_BASE_DATA_DIR 'local-login.json'
if (-not (Test-Path -LiteralPath $LoginPath)) {
    New-Item -ItemType Directory -Path $env:LABEL_STUDIO_BASE_DATA_DIR -Force | Out-Null
    @{ username='stockradar@localhost'; password=([Guid]::NewGuid().ToString('N') + 'A!9') } |
        ConvertTo-Json | Set-Content -LiteralPath $LoginPath -Encoding utf8
}
$Login = Get-Content -LiteralPath $LoginPath -Raw | ConvertFrom-Json
$env:LABEL_STUDIO_USERNAME = $Login.username
$env:LABEL_STUDIO_PASSWORD = $Login.password

Write-Host "Label Studio local-files root: $DataRoot"
Write-Host "Single config: labeling/vision-single.xml"
Write-Host "Pair config:   labeling/vision-pair.xml"
Write-Host "Pilot tasks:   data/vision-research/pilot-v1/"
Write-Host "Local login is stored in data/vision-research/label-studio/local-login.json"
& $Python (Join-Path $PSScriptRoot 'start_label_studio_wsgi.py') start --host "http://localhost:$Port" --internal-host 127.0.0.1 --port $Port --no-browser
if ($LASTEXITCODE -ne 0) { throw 'Label Studio exited with an error.' }
