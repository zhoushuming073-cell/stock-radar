param(
    [Parameter(Mandatory = $true)]
    [string]$SiteOrigin
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $pythonw)) { throw 'Python environment is incomplete' }
if ($SiteOrigin -notmatch '^https://[A-Za-z0-9.-]+$') { throw 'SiteOrigin must be an HTTPS origin without a path' }

$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
$dailySettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$apiSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

# 08:30 China local time on Tuesday-Saturday follows the US Monday-Friday close.
$dailyTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday,Wednesday,Thursday,Friday,Saturday -At '08:30'
$catchupTrigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$dailyAction = New-ScheduledTaskAction -Execute $pythonw -Argument '-m radar.daily_update --if-due' -WorkingDirectory $root
Register-ScheduledTask -TaskName 'StockRadar-DailyUpdate' -Action $dailyAction -Trigger @($dailyTrigger,$catchupTrigger) -Settings $dailySettings -Principal $principal -Description 'Quietly update local Alpaca daily bars at 08:30 or catch up on next logon' -Force | Out-Null

$apiTrigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$apiAction = New-ScheduledTaskAction -Execute $pythonw -Argument "-m radar.local_api --port 8765 --allow-origin $SiteOrigin" -WorkingDirectory $root
Register-ScheduledTask -TaskName 'StockRadar-LocalApi' -Action $apiAction -Trigger $apiTrigger -Settings $apiSettings -Principal $principal -Description 'Read-only loopback API for the private Stock Radar Site' -Force | Out-Null

Get-ScheduledTask -TaskName 'StockRadar-DailyUpdate','StockRadar-LocalApi' |
    Select-Object TaskName,State,@{Name='NextRunTime';Expression={(Get-ScheduledTaskInfo -TaskName $_.TaskName).NextRunTime}}
