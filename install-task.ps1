# Registers a Windows scheduled task "NewTermRadar" for the current user.
# Usage: powershell -ExecutionPolicy Bypass -File install-task.ps1 [-StartHour 9]
param([int]$StartHour = 9)
$dir = $PSScriptRoot
$arg = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$dir\run-daily.ps1`" -StartHour $StartHour"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arg -WorkingDirectory $dir

# Daily at StartHour, repeated hourly until midnight (covers late boots and retries)
$daily = New-ScheduledTaskTrigger -Daily -At ("{0:D2}:00" -f $StartHour)
$hours = 24 - $StartHour
$daily.Repetition = (New-ScheduledTaskTrigger -Once -At "00:00" -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Hours $hours)).Repetition

# Also at logon, 3 minutes after you sign in
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$logon.Delay = "PT3M"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "NewTermRadar" -Action $action -Trigger @($daily, $logon) -Settings $settings `
    -Description "new-term-radar: run once per day after ${StartHour}:00" -Force | Out-Null
Write-Host "Task 'NewTermRadar' installed: runs once a day after $StartHour`:00, logs in $dir\logs"
