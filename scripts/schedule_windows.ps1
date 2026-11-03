# Регистрирует ежедневную задачу в Планировщике заданий Windows.
# Пример: powershell -ExecutionPolicy Bypass -File scripts\schedule_windows.ps1 -Time 09:00 -WithLetters
# Удалить задачу: Unregister-ScheduledTask -TaskName JobHuntAssistant
param([string]$Time = "09:00", [switch]$WithLetters)

$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot "daily.ps1"
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
if ($WithLetters) { $arguments += " -WithLetters" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName "JobHuntAssistant" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Сбор вакансий JobHuntAssistant" -Force | Out-Null
Write-Host "Задача JobHuntAssistant: каждый день в $Time. Лог: $repo\logs\"
