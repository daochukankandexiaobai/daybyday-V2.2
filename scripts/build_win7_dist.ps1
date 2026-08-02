param(
    [string]$DistPath = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SpecPath = Join-Path $ProjectRoot "TeamReportApp_win7.spec"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python 3.8 virtual environment was not found: $PythonExe"
}

if ([string]::IsNullOrWhiteSpace($DistPath)) {
    $DistPath = Join-Path $ProjectRoot "dist"
}

$WorkPath = Join-Path $ProjectRoot "build\day_by_day"

Push-Location $ProjectRoot
try {
    & $PythonExe -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath $DistPath `
        --workpath $WorkPath `
        $SpecPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$ExePath = Join-Path $DistPath "day by day\day by day.exe"
if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "Build output was not found: $ExePath"
}

Write-Host "Build completed: $ExePath"
