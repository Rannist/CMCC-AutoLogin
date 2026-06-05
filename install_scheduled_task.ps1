# CMCC Auto Login - Startup Script
# Create a current-user scheduled task instead of a Startup .lnk shortcut.

$ErrorActionPreference = "Stop"

$taskName = "CMCCAutoLogin"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appDir = $scriptDir
if ((Split-Path -Leaf $scriptDir) -ieq "scripts") {
    $appDir = Split-Path -Parent $scriptDir
}
$loginScript = Join-Path $scriptDir "StartupAutoLogin.ps1"
$launcherScript = Join-Path $scriptDir "StartupAutoLogin.vbs"
$wscriptPath = Join-Path $env:WINDIR "System32\wscript.exe"
$startupDir = [Environment]::GetFolderPath("Startup")
$oldStartupItems = @(
    (Join-Path $startupDir "AutoLogin.lnk"),
    (Join-Path $startupDir "CmccAutoLogin.lnk"),
    (Join-Path $startupDir "CmccAutoLogin.cmd"),
    (Join-Path $startupDir "CMCC_AutoLogin.lnk")
)

Write-Host "Script directory: $scriptDir"
Write-Host "App directory: $appDir"
Write-Host "Login script: $loginScript"
Write-Host "Launcher script: $launcherScript"
Write-Host "Windows Script Host path: $wscriptPath"
Write-Host "Task name: $taskName"

if (-not (Test-Path -LiteralPath $loginScript)) {
    Write-Host "Error: Cannot find $loginScript"
    exit 1
}

if (-not (Test-Path -LiteralPath $launcherScript)) {
    Write-Host "Error: Cannot find $launcherScript"
    exit 1
}

if (-not (Test-Path -LiteralPath $wscriptPath)) {
    Write-Host "Error: Cannot find $wscriptPath"
    exit 1
}

foreach ($path in $oldStartupItems) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
        Write-Host "Cleaned old startup item: $path"
    }
}

try {
    $taskArgs = "//B //Nologo `"$launcherScript`""
    $action = New-ScheduledTaskAction -Execute $wscriptPath -Argument $taskArgs -WorkingDirectory $appDir
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

    Write-Host "Success: Startup scheduled task added"
    Write-Host "Startup fast login script will run at user logon without opening the main GUI"
    exit 0
}
catch {
    Write-Host "Error: Failed to create scheduled task - $($_.Exception.Message)"
    exit 1
}
