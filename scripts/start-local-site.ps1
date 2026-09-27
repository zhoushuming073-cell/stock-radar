$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
$apiUrl = 'http://127.0.0.1:8765'
$siteUrl = 'http://localhost:4174'
$streamlitUrl = 'http://127.0.0.1:8502'
$taskName = 'StockRadar-LocalApi'

if (-not (Test-Path -LiteralPath $pythonw)) {
    throw "Python environment is missing: $pythonw"
}

function Test-LocalApi {
    try {
        $response = Invoke-WebRequest -Uri "$apiUrl/health" -UseBasicParsing -TimeoutSec 2
        $body = $response.Content | ConvertFrom-Json
        return $response.StatusCode -eq 200 -and $body.ok -eq $true
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
        $response = Invoke-WebRequest -Uri "$siteUrl/lab.html" -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200 -and $response.Content.Contains('Stock Radar')
    } catch {
        return $false
    }
}

function Test-Streamlit {
    try {
        $response = Invoke-WebRequest -Uri "$streamlitUrl/_stcore/health" -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200 -and $response.Content.Trim() -eq 'ok'
    } catch {
        return $false
    }
}

if (-not (Test-LocalApi) -or -not (Test-ApiOrigin)) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        if ($task.State -eq 'Running') {
            Stop-ScheduledTask -TaskName $taskName
            Start-Sleep -Milliseconds 500
        }
        Start-ScheduledTask -TaskName $taskName
    } elseif (Test-LocalApi) {
        throw 'The running API does not allow the local site. Close it, then run this launcher again.'
    } else {
        Start-Process -FilePath $pythonw -ArgumentList '-m', 'radar.local_api', '--port', '8765' -WorkingDirectory $root -WindowStyle Hidden
    }

    for ($attempt = 0; $attempt -lt 30 -and (-not (Test-LocalApi) -or -not (Test-ApiOrigin)); $attempt++) {
        Start-Sleep -Milliseconds 500
    }
}

if (-not (Test-LocalApi) -or -not (Test-ApiOrigin)) {
    throw 'The local API did not start on port 8765.'
}

if (-not (Test-LocalSite)) {
    $siteScript = Join-Path $root 'scripts\serve-local-site.py'
    Start-Process -FilePath $pythonw -ArgumentList "`"$siteScript`"" -WorkingDirectory $root -WindowStyle Hidden
    for ($attempt = 0; $attempt -lt 30 -and -not (Test-LocalSite); $attempt++) {
        Start-Sleep -Milliseconds 500
    }
}

if (-not (Test-LocalSite)) {
    throw 'The local site did not start. Check whether port 4174 is occupied.'
}

if (-not (Test-Streamlit)) {
    Start-Process -FilePath $pythonw -ArgumentList '-m', 'streamlit', 'run', 'src/radar/strategy_lab_ui.py', '--server.port', '8502', '--server.address', '127.0.0.1', '--server.headless', 'true' -WorkingDirectory $root -WindowStyle Hidden
    for ($attempt = 0; $attempt -lt 40 -and -not (Test-Streamlit); $attempt++) {
        Start-Sleep -Milliseconds 500
    }
}

if (-not (Test-Streamlit)) {
    throw 'The Streamlit Lab did not start on port 8502.'
}

Start-Process "$streamlitUrl/"
Start-Process "$siteUrl/lab.html#scanner"
