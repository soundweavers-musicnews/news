<#
.SYNOPSIS
  Daily runner for SoundWeavers Music Tech News:
  1. Runs Python pipeline (fetch news -> Gemini analysis -> GPT-SoVITS TTS -> 30s hand-drawn video)
  2. Commits & pushes `site/` to https://github.com/soundweavers-musicnews
#>
param(
    [switch]$SkipTTS,
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# Optional: load local .env if present (for GEMINI_API_KEY)
$EnvFile = Join-Path $RepoRoot ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match "^\s*([^#][^=]+)=(.*)$") {
            [Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), "Process")
        }
    }
}

$PyArgs = @("pipeline/run_daily.py")
if ($SkipTTS) { $PyArgs += "--skip-tts" }

Write-Host "=== Running SoundWeavers Music News Pipeline ===" -ForegroundColor Cyan
& python @PyArgs
if ($LASTEXITCODE -ne 0) {
    throw "Pipeline failed with exit code $LASTEXITCODE"
}

if ($NoPush) {
    Write-Host "=== -NoPush specified; skipping Git push ===" -ForegroundColor Yellow
    exit 0
}

$GitCmd = Get-Command git -ErrorAction SilentlyContinue
if (-not $GitCmd) {
    Write-Warning "git is not installed or not in PATH. Install Git for Windows (winget install Git.Git) to enable auto-push to https://github.com/soundweavers-musicnews"
    exit 0
}

if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
    Write-Host "Initializing Git repo and linking remote https://github.com/soundweavers-musicnews/news.git ..."
    git init
    git branch -M main
    git remote add origin https://github.com/soundweavers-musicnews/news.git
}

git add site/ config.yaml pipeline/ scripts/ README.md .gitignore
$Status = git status --porcelain
if (-not $Status) {
    Write-Host "No changes to commit." -ForegroundColor Green
    exit 0
}

$Stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
git commit -m "chore(news): daily music tech broadcast update ($Stamp)"
git push -u origin main
Write-Host "=== Deployed to https://github.com/soundweavers-musicnews ===" -ForegroundColor Green
