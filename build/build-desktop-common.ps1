function Test-Command {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )
    return [bool](Get-Command -Name $Name -ErrorAction SilentlyContinue)
}

function Assert-Command {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$InstallHint
    )
    if (-not (Test-Command -Name $Name)) {
        throw "Команда '$Name' не найдена. $InstallHint"
    }
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Description,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string[]]$Command
    )
    Write-Host "==> $Description" -ForegroundColor Cyan
    $previousLocation = (Get-Location).Path
    try {
        Set-Location -LiteralPath $WorkingDirectory
        $commandArguments = @()
        if ($Command.Count -gt 1) {
            $commandArguments = $Command[1..($Command.Count - 1)]
        }
        & $Command[0] @commandArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Шаг завершился с ошибкой (код $LASTEXITCODE): $Description"
        }
    }
    finally {
        Set-Location -LiteralPath $previousLocation
    }
}
