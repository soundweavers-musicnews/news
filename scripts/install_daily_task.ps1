<#
.SYNOPSIS
  Registers a Windows Task Scheduler job to run the daily music news pipeline & GitHub push.
#>
param(
    [string]$RunTime = "08:30",
    [string]$TaskName = "SoundWeaversMusicNewsDaily"
)

$ErrorActionPreference = "Stop"
$ScriptPath = Join-Path $PSScriptRoot "run_and_deploy.ps1"

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

$Trigger = New-ScheduledTaskTrigger -Daily -At $RunTime
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Daily SoundWeavers Music Tech News fetch, Gemini analysis, GPT-SoVITS TTS, hand-drawn 30s video, and GitHub push." `
    -Force

Write-Host "Scheduled task '$TaskName' installed! Will run daily at $RunTime." -ForegroundColor Green
