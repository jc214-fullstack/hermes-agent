param(
    [Parameter(Mandatory=$true)]
    [string]$Url,

    [string]$OutDir
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $OutDir -or [string]::IsNullOrWhiteSpace($OutDir)) {
    $OutDir = Join-Path $scriptDir '..\output'
}

$resolvedOutDir = [System.IO.Path]::GetFullPath($OutDir)
New-Item -ItemType Directory -Force -Path $resolvedOutDir | Out-Null

$template = Join-Path $resolvedOutDir '%(id)s.%(ext)s'

Write-Host "Downloading Instagram reel..." -ForegroundColor Cyan
Write-Host "URL: $Url"
Write-Host "Output dir: $resolvedOutDir"

& yt-dlp --no-playlist --restrict-filenames -o $template $Url
if ($LASTEXITCODE -ne 0) {
    throw "yt-dlp failed with exit code $LASTEXITCODE"
}

$latest = Get-ChildItem -Path $resolvedOutDir -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $latest) {
    throw "Download completed but no output file was found."
}

Write-Host "DONE: $($latest.FullName)" -ForegroundColor Green
Write-Output $latest.FullName
