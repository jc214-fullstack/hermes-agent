param(
    [Parameter(Mandatory=$true)]
    [string]$InputVideo,

    [string]$OutDir,

    [int]$FrameIntervalSeconds = 8
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $InputVideo)) {
    throw "Input video not found: $InputVideo"
}

if (-not $OutDir -or [string]::IsNullOrWhiteSpace($OutDir)) {
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($InputVideo)
    $OutDir = Join-Path ([System.IO.Path]::GetDirectoryName($InputVideo)) ($baseName + '-analysis')
}

$resolvedOutDir = [System.IO.Path]::GetFullPath($OutDir)
New-Item -ItemType Directory -Force -Path $resolvedOutDir | Out-Null

$audioPath = Join-Path $resolvedOutDir 'audio.wav'
$framePattern = Join-Path $resolvedOutDir 'frame-%03d.jpg'
$fpsExpr = "fps=1/$FrameIntervalSeconds,scale=960:-1"

Write-Host "Extracting audio..." -ForegroundColor Cyan
& ffmpeg -y -i $InputVideo -vn -ac 1 -ar 16000 $audioPath
if ($LASTEXITCODE -ne 0) { throw "ffmpeg audio extraction failed" }

Write-Host "Sampling frames..." -ForegroundColor Cyan
& ffmpeg -y -i $InputVideo -vf $fpsExpr $framePattern
if ($LASTEXITCODE -ne 0) { throw "ffmpeg frame extraction failed" }

Write-Host "DONE: $resolvedOutDir" -ForegroundColor Green
Write-Output $resolvedOutDir
