$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
$apiUrl = 'http://127.0.0.1:8765'
$siteUrl = 'http://127.0.0.1:4174'
$taskName = 'StockRadar-LocalApi'

if (-not (Test-Path -LiteralPath $pythonw)) {
    throw "Python environment is missing: $pythonw"
}

function Test-LocalApi {
    try {
        $response = Invoke-WebRequest -Uri "$apiUrl/health" -UseBasicParsing -TimeoutSec 2
        $body = $response.Content | ConvertFrom-Json
        return $response.StatusCode -eq 200 -and $body.ok -eq $true -and $body.service -eq 'stock-radar-api'
    } catch {
        return $false
    }
}

function Test-ApiOrigin {
    try {
        $response = Invoke-WebRequest -Method Options -Uri "$apiUrl/api/lab/run" -UseBasicParsing -TimeoutSec 2 -Headers @{
            Origin = $siteUrl
            'Access-Control-Request-Method' = 'POST'
        }
        return $response.StatusCode -eq 204 -and $response.Headers['Access-Control-Allow-Origin'] -contains $siteUrl
    } catch {
        return $false
    }
}

function Test-LocalSite {
    try {
        $health = Invoke-WebRequest -Uri "$siteUrl/health" -UseBasicParsing -TimeoutSec 2
        $body = $health.Content | ConvertFrom-Json
        if ($health.StatusCode -ne 200 -or $body.ok -ne $true -or $body.service -ne 'stock-radar-web') {
            return $false
        }
        $page = Invoke-WebRequest -Uri "$siteUrl/lab.html" -UseBasicParsing -TimeoutSec 2
        return $page.StatusCode -eq 200 -and $page.Content.Contains('Stock Radar')
    } catch {
        return $false
    }
}

function Get-ListenerPids([int]$port) {
    @(
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
}

function Assert-PortFree([int]$port) {
    $owners = @(Get-ListenerPids $port)
    if ($owners.Count -gt 0) {
        throw "Port $port is occupied by PID(s) $($owners -join ', '), but the Stock Radar service is not healthy. Inspect those processes and free the port before retrying."
    }
}

if (-not (Test-LocalApi) -or -not (Test-ApiOrigin)) {
    Assert-PortFree 8765
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        if ($task.State -eq 'Running') {
            Stop-ScheduledTask -TaskName $taskName
        }
        Start-ScheduledTask -TaskName $taskName
    } else {
        Start-Process -FilePath $pythonw -ArgumentList '-m', 'radar.local_api', '--port', '8765' -WorkingDirectory $root -WindowStyle Hidden
    }
    for ($attempt = 0; $attempt -lt 30 -and (-not (Test-LocalApi) -or -not (Test-ApiOrigin)); $attempt++) {
        Start-Sleep -Milliseconds 500
    }
}
if (-not (Test-LocalApi) -or -not (Test-ApiOrigin)) {
    throw 'The Stock Radar API did not become healthy on port 8765. Check the scheduled task or local API process.'
}

if (-not (Test-LocalSite)) {
    Assert-PortFree 4174
    $siteScript = Join-Path $root 'scripts\serve-local-site.py'
    Start-Process -FilePath $pythonw -ArgumentList "`"$siteScript`"" -WorkingDirectory $root -WindowStyle Hidden
    for ($attempt = 0; $attempt -lt 30 -and -not (Test-LocalSite); $attempt++) {
        Start-Sleep -Milliseconds 500
    }
}
if (-not (Test-LocalSite)) {
    throw 'The Stock Radar Web UI did not become healthy on port 4174.'
}

Start-Process "$siteUrl/lab.html#scanner"
