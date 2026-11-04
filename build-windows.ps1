$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'build\build-desktop-common.ps1')

$repoRoot = $PSScriptRoot
$backendDir = Join-Path $repoRoot 'backend'
$webDir = Join-Path $repoRoot 'frontend\web'
$desktopDir = Join-Path $repoRoot 'frontend\desktop'
$desktopReleaseDir = Join-Path $desktopDir 'release'
$artifactsDir = Join-Path $repoRoot 'build\dist'

try {
    Assert-Command -Name 'uv' -InstallHint 'Установите uv: https://docs.astral.sh/uv/getting-started/installation/'
    Assert-Command -Name 'node' -InstallHint 'Установите Node.js LTS: https://nodejs.org/ru/download'
    Assert-Command -Name 'npm' -InstallHint 'npm входит в состав Node.js: https://nodejs.org/ru/download'

    Write-Host '=== Сборка VibeSolver (Windows) ===' -ForegroundColor Green

    Invoke-NativeCommand -Description 'Backend: установка зависимостей (uv sync)' -WorkingDirectory $backendDir -Command @('uv', 'sync')
    Invoke-NativeCommand -Description 'Backend: тесты (pytest)' -WorkingDirectory $backendDir -Command @('uv', 'run', 'pytest')
    Invoke-NativeCommand -Description 'Backend: линтер (ruff)' -WorkingDirectory $backendDir -Command @('uv', 'run', 'ruff', 'check', '.')
    Invoke-NativeCommand -Description 'Backend: типизация (mypy)' -WorkingDirectory $backendDir -Command @('uv', 'run', 'mypy', 'app')

    Invoke-NativeCommand -Description 'Frontend: установка зависимостей (npm ci)' -WorkingDirectory $webDir -Command @('npm', 'ci')
    Invoke-NativeCommand -Description 'Frontend: линтер (eslint)' -WorkingDirectory $webDir -Command @('npm', 'run', 'lint')
    Invoke-NativeCommand -Description 'Frontend: тесты (vitest)' -WorkingDirectory $webDir -Command @('npm', 'run', 'test')
    Invoke-NativeCommand -Description 'Frontend: сборка (vite build)' -WorkingDirectory $webDir -Command @('npm', 'run', 'build')

    Invoke-NativeCommand -Description 'Desktop: установка зависимостей (npm ci)' -WorkingDirectory $desktopDir -Command @('npm', 'ci')
    Invoke-NativeCommand -Description 'Desktop: компиляция (tsc)' -WorkingDirectory $desktopDir -Command @('npm', 'run', 'build')
    Invoke-NativeCommand -Description 'Desktop: копирование веб-сборки' -WorkingDirectory $desktopDir -Command @('node', 'scripts\copy-web.mjs')
    Invoke-NativeCommand -Description 'Desktop: сборка установщика (electron-builder)' -WorkingDirectory $desktopDir -Command @('npx', 'electron-builder', '--win', 'nsis')

    $setupFiles = @(Get-ChildItem -Path $desktopReleaseDir -Filter 'VibeSolver-Setup-*.exe' -ErrorAction SilentlyContinue)
    if ($setupFiles.Count -eq 0) {
        throw "Установщик не найден в '$desktopReleaseDir'. Проверьте журнал electron-builder."
    }
    $setupFile = $setupFiles | Sort-Object -Property LastWriteTime -Descending | Select-Object -First 1
    New-Item -ItemType Directory -Path $artifactsDir -Force | Out-Null
    $destinationPath = Join-Path $artifactsDir $setupFile.Name
    Copy-Item -LiteralPath $setupFile.FullName -Destination $destinationPath -Force

    Write-Host ''
    Write-Host 'Сборка успешно завершена.' -ForegroundColor Green
    Write-Host "Установщик: $destinationPath" -ForegroundColor Green
    exit 0
}
catch {
    Write-Host "Сборка прервана: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
