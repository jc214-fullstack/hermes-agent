param(
    [Parameter(Mandatory=$true)]
    [string]$InputVideo
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$extractScript = Join-Path $scriptDir 'extract_media.ps1'

Write-Host "STEP 1/2: extract media" -ForegroundColor Cyan
$extractOutput = powershell -ExecutionPolicy Bypass -File $extractScript -InputVideo $InputVideo
$analysisDir = ($extractOutput | Select-Object -Last 1).ToString().Trim()

Write-Host "STEP 2/2: report outputs" -ForegroundColor Cyan
$files = Get-ChildItem -Path $analysisDir -File | Sort-Object Name
$files | Select-Object Name,Length

Write-Host "Analysis dir: $analysisDir" -ForegroundColor Green
Write-Output $analysisDir
