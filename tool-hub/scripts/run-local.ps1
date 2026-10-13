<#
.SYNOPSIS
  Run LeadGen AI on Windows without Docker.

.DESCRIPTION
  Starts the five step services (Find Demand, Check Fit, Find Leads, Win Leads, Reach Out),
  Proof Library (video-scraper) and the web app against a local PostgreSQL.
  Proof Library also needs FFmpeg (winget install Gyan.FFmpeg) and Playwright Chromium
  (.venv-local\Scripts\python -m playwright install chromium). It stores media in
  .local-media unless MEDIA_DIR is set, and MinIO stays off (MINIO_ENABLED=false).

  One-time setup:
    1. PostgreSQL 16 running on localhost:5432 with a `toolhub` user/database
       (password `toolhub`) and infra/init-db.sql applied.
    2. python -m venv .venv-local
       .venv-local\Scripts\pip install -r <requirements of the 5 backends>
    3. Copy .env.example to .env and point DATABASE_URL and *_API_URL at localhost.

.EXAMPLE
  .\scripts\run-local.ps1           # start everything
  .\scripts\run-local.ps1 -Stop     # stop everything
  .\scripts\run-local.ps1 -Status   # show what is running
  .\scripts\run-local.ps1 -Restart "Find Leads","Reach Out"   # restart some services
#>
param(
  [switch]$Stop,
  [switch]$Status,
  [switch]$Rebuild,
  [string[]]$Restart = @()
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root ".local-logs"
$PidFile = Join-Path $LogDir "pids.json"
$Python = Join-Path $Root ".venv-local\Scripts\python.exe"
$NextBin = Join-Path $Root "node_modules\next\dist\bin\next"

$Services = @(
  @{ Name = "Proof Library"; Dir = "modules\video-scraper\backend"; Port = 8101 },
  @{ Name = "Find Demand"; Dir = "modules\market-depth-analyzer\backend"; Port = 8102 },
  @{ Name = "Find Leads";  Dir = "modules\lead-intelligence\backend";     Port = 8103 },
  @{ Name = "Check Fit";   Dir = "modules\build-readiness\backend";       Port = 8104 },
  @{ Name = "Win Leads";   Dir = "modules\growth-pillars\backend";        Port = 8105 },
  @{ Name = "Reach Out";   Dir = "modules\outreach-autopilot\backend";    Port = 8106 }
)
$WebPort = 3200

function Stop-PortListener([int]$Port) {
  Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

function Test-Port([int]$Port) {
  [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Show-Status {
  foreach ($s in $Services) {
    $state = if (Test-Port $s.Port) { "running" } else { "stopped" }
    "{0,-14} http://localhost:{1}  {2}" -f $s.Name, $s.Port, $state
  }
  $webState = if (Test-Port $WebPort) { "running" } else { "stopped" }
  "{0,-14} http://localhost:{1}  {2}" -f "Web app", $WebPort, $webState
}

if ($Status) { Show-Status; return }

if ($Stop) {
  if (Test-Path $PidFile) {
    (Get-Content $PidFile | ConvertFrom-Json) | ForEach-Object {
      Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $PidFile -Force
  }
  # uvicorn/next may leave child processes holding the port
  foreach ($s in $Services) { Stop-PortListener $s.Port }
  Stop-PortListener $WebPort
  "Stopped."
  return
}

if (-not (Test-Path $Python)) { throw "Missing $Python. Create .venv-local first (see the header of this script)." }
if (-not (Test-Path (Join-Path $Root ".env"))) { throw "Missing .env. Copy .env.example to .env first." }

# Load .env into this process so every child inherits it
Get-Content (Join-Path $Root ".env") | ForEach-Object {
  $line = $_.Trim()
  if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { return }
  $key, $value = $line.Split("=", 2)
  [Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), "Process")
}

# Proof Library: local media folder, no MinIO, and FFmpeg on PATH
if (-not $env:MEDIA_DIR) { $env:MEDIA_DIR = Join-Path $Root ".local-media" }
New-Item -ItemType Directory -Force -Path $env:MEDIA_DIR | Out-Null
if (-not $env:MINIO_ENABLED) { $env:MINIO_ENABLED = "false" }
if (-not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
  $ffprobe = Get-ChildItem (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages") -Directory -Filter "Gyan.FFmpeg*" -ErrorAction SilentlyContinue |
    ForEach-Object { Get-ChildItem $_.FullName -Recurse -Filter ffprobe.exe -ErrorAction SilentlyContinue } |
    Select-Object -First 1
  if ($ffprobe) { $env:PATH = "$($ffprobe.DirectoryName);$env:PATH" }
  else { "WARNING: FFmpeg not found. Proof Library can't download or transcribe videos. Run: winget install Gyan.FFmpeg" }
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$pids = @()

foreach ($name in $Restart) {
  if ($name -eq "Web app") { Stop-PortListener $WebPort; continue }
  $svc = $Services | Where-Object { $_.Name -eq $name }
  if (-not $svc) { throw "Unknown service '$name'. Use one of: $(($Services.Name + 'Web app') -join ', ')" }
  Stop-PortListener $svc.Port
}
if ($Restart.Count -gt 0) { Start-Sleep -Seconds 2 }

foreach ($s in $Services) {
  if (Test-Port $s.Port) { "{0} already running on {1}" -f $s.Name, $s.Port; continue }
  $name = ($s.Name -replace " ", "-").ToLower()
  $proc = Start-Process -FilePath $Python `
    -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", $s.Port `
    -WorkingDirectory (Join-Path $Root $s.Dir) `
    -RedirectStandardOutput (Join-Path $LogDir "$name.out.log") `
    -RedirectStandardError (Join-Path $LogDir "$name.err.log") `
    -WindowStyle Hidden -PassThru
  $pids += $proc.Id
  "Started {0} on http://localhost:{1}" -f $s.Name, $s.Port
}

$WebDir = Join-Path $Root "apps\web"
if ($Rebuild -or -not (Test-Path (Join-Path $WebDir ".next\BUILD_ID"))) {
  "Building the web app (first run takes about a minute)..."
  Push-Location $Root
  try { npm run build -w apps/web | Out-Null } finally { Pop-Location }
}

if (Test-Port $WebPort) {
  "Web app already running on $WebPort"
} else {
  $proc = Start-Process -FilePath "node" `
    -ArgumentList $NextBin, "start", "-p", $WebPort `
    -WorkingDirectory $WebDir `
    -RedirectStandardOutput (Join-Path $LogDir "web.out.log") `
    -RedirectStandardError (Join-Path $LogDir "web.err.log") `
    -WindowStyle Hidden -PassThru
  $pids += $proc.Id
  "Started web app on http://localhost:$WebPort"
}

$existing = if (Test-Path $PidFile) { @(Get-Content $PidFile | ConvertFrom-Json) } else { @() }
ConvertTo-Json -InputObject @($existing + $pids) | Set-Content $PidFile

"Waiting for services to come up..."
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
  $down = @($Services | Where-Object { -not (Test-Port $_.Port) })
  if ($down.Count -eq 0 -and (Test-Port $WebPort)) { break }
  Start-Sleep -Seconds 2
}
""
Show-Status
""
"Open http://localhost:$WebPort and sign in with admin@toolhub.local / your HUB_ADMIN_PASSWORD."
"Logs: $LogDir    Stop everything: .\scripts\run-local.ps1 -Stop"
