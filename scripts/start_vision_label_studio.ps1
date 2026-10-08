param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [switch]$Install
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
    py -3.11 -m venv $Venv
}

if ($Install -or -not (Test-Path $LabelStudio)) {
    & $Python -m pip install --upgrade pip
    & $Python -m pip install "label-studio>=1.23,<2"
}

$env:LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED = "true"
$env:LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT = $DataRoot

Write-Host "Label Studio local-files root: $DataRoot"
Write-Host "Single config: labeling/vision-single.xml"
Write-Host "Pair config:   labeling/vision-pair.xml"
Write-Host "Pilot tasks:   data/vision-research/pilot-v1/"
& $LabelStudio start
