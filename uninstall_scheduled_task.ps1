$ErrorActionPreference = "Stop"
$removed = $false
$taskName = "CMCCAutoLogin"

try {
    $taskResult = & schtasks.exe /Query /TN $taskName 2>$null
    if ($LASTEXITCODE -eq 0) {
        $deleteResult = & schtasks.exe /Delete /TN $taskName /F 2>&1
        foreach ($line in $deleteResult) {
            if ($line) {
                Write-Host $line
            }
        }

        if ($LASTEXITCODE -eq 0) {
            Write-Host "Scheduled task removed ($taskName)"
            $removed = $true
        }
        else {
            Write-Host "Error removing scheduled task ($taskName). Exit code: $LASTEXITCODE"
        }
    }

    $startupDir = [Environment]::GetFolderPath("Startup")
    $startupItems = @(
        (Join-Path $startupDir "AutoLogin.lnk"),
        (Join-Path $startupDir "CmccAutoLogin.lnk"),
        (Join-Path $startupDir "CmccAutoLogin.cmd"),
        (Join-Path $startupDir "CMCC_AutoLogin.lnk")
    )

    foreach ($path in $startupItems) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
            Write-Host "Cleaned up old startup item: $path"
            $removed = $true
        }
    }
}
catch {
    Write-Host "Error removing startup: $($_.Exception.Message)"
}

if (-not $removed) {
    Write-Host "No auto login startup items found to remove"
}
