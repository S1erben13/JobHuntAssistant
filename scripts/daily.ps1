# Дневной запуск: сбор вакансий и (по желанию) письма через Claude Code.
# Пример: powershell -ExecutionPolicy Bypass -File scripts\daily.ps1 -WithLetters
param([switch]$WithLetters)

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$py = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

# OUTPUT_DIR из .env, иначе ~/Documents/JobHunt (так же, как в run.py)
$out = Join-Path $HOME "Documents\JobHunt"
if (Test-Path ".env") {
    $line = Get-Content ".env" | Where-Object { $_ -match '^\s*OUTPUT_DIR\s*=' } | Select-Object -First 1
    if ($line) { $out = ($line -split '=', 2)[1].Trim().Trim('"') }
}

$logDir = Join-Path $repo "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("daily-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

& $py run.py *>> $log

if ($WithLetters) {
    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
        "claude не найден в PATH — письма пропущены" | Out-File -Append $log
        exit 0
    }
    claude -p "Выполни скилл job-letters. Сбор вакансий уже сделан, начни с шага 3." `
        --allowedTools "Read" "Write" "Edit" "Glob" `
        --add-dir "$out" *>> $log
}
