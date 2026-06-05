﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = $ScriptDir
if ((Split-Path -Leaf $ScriptDir) -ieq "scripts") {
    $AppDir = Split-Path -Parent $ScriptDir
}
$ConfigFile = Join-Path $AppDir "config.json"
$LogFile = Join-Path $AppDir "autologin.log"
$StartupTaskName = "CMCCAutoLogin"
$StartupDir = [Environment]::GetFolderPath("Startup")
$OldStartupItems = @(
    (Join-Path $StartupDir "AutoLogin.lnk"),
    (Join-Path $StartupDir "CmccAutoLogin.lnk"),
    (Join-Path $StartupDir "CmccAutoLogin.cmd"),
    (Join-Path $StartupDir "CMCC_AutoLogin.lnk")
)

function Invoke-Tool {
    param(
        [string]$ScriptPath,
        [string[]]$ScriptArguments = @()
    )

    $escapedScriptPath = $ScriptPath.Replace("'", "''")
    $escapedArguments = @()
    foreach ($argument in $ScriptArguments) {
        if ($argument -match '^-') {
            $escapedArguments += $argument
        }
        else {
            $escapedArguments += "'" + $argument.Replace("'", "''") + "'"
        }
    }
    $encodedArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command",
        "[Console]::InputEncoding=[Text.Encoding]::UTF8; [Console]::OutputEncoding=[Text.Encoding]::UTF8; & '$escapedScriptPath' $($escapedArguments -join ' '); exit `$LASTEXITCODE"
    )
    $process = Start-Process -FilePath "powershell.exe" -ArgumentList $encodedArgs -NoNewWindow -Wait -PassThru
    return $process.ExitCode
}

function Show-AlreadyOnlineMessage {
    param([string]$ContinueText = "按回车进入功能菜单...")

    Write-Host ""
    Write-Host "当前状态: 已联网" -ForegroundColor Green
    Write-Host "现在不需要设置校园网账号密码。"
    Write-Host "如果要配置自动登录，请先连接到未登录的校园网，让电脑处于无法上网/等待认证的状态，然后再选择 1。"
    Write-Host ""
    Write-Host $ContinueText
}

function Start-AccountSetup {
    $loginScript = Join-Path $ScriptDir "AutoLogin.ps1"
    $precheckExitCode = Invoke-Tool $loginScript @("-Setup", "-Quiet")
    if ($precheckExitCode -eq 10) {
        Show-AlreadyOnlineMessage
        Read-Host | Out-Null
        return 10
    }

    Write-Host "CMCC 自动登录账号设置"
    Write-Host ""

    $userName = ""
    while ([string]::IsNullOrWhiteSpace($userName)) {
        $userName = Read-Host "请输入账号"
        if ([string]::IsNullOrWhiteSpace($userName)) {
            Write-Host "账号不能为空。" -ForegroundColor Yellow
        }
    }

    $attempt = 0
    while ($true) {
        $attempt++
        $password = Read-Host "请输入密码"
        if ([string]::IsNullOrWhiteSpace($password)) {
            Write-Host "密码不能为空。" -ForegroundColor Yellow
            continue
        }

        Write-Host ("正在验证账号密码，第 {0} 次，请稍候..." -f $attempt)
        $exitCode = Invoke-Tool $loginScript @("-Setup", "-Quiet", "-SetupUserName", $userName, "-SetupPassword", $password)
        if ($exitCode -eq 0) {
            Write-Host "联网确认成功，账号密码已通过验证并保存。" -ForegroundColor Green
            Write-Host "提示：Windows 右下角网络图标可能会延迟 1-2 秒。"
            Start-Sleep -Seconds 2
            return 0
        }
        elseif ($exitCode -eq 10) {
            Show-AlreadyOnlineMessage
            Read-Host | Out-Null
            return 10
        }
        elseif ($exitCode -eq 20) {
            Write-Host "验证失败：账号或密码错误，或登录后没有检测到联网成功。请重新输入密码。" -ForegroundColor Yellow
            Write-Host ""
        }
        else {
            Write-Host ("账号密码设置未完成。退出码: " + $exitCode) -ForegroundColor Yellow
            Write-Host "请确认当前连接的是未登录的校园网，并查看日志了解具体原因。"
            return $exitCode
        }
    }
}

function Test-ConfigReady {
    if (-not (Test-Path -LiteralPath $ConfigFile)) {
        return $false
    }

    try {
        $config = Get-Content -Raw -LiteralPath $ConfigFile | ConvertFrom-Json
        return (-not [string]::IsNullOrWhiteSpace($config.UserName) -and -not [string]::IsNullOrWhiteSpace($config.ProtectedPassword))
    }
    catch {
        return $false
    }
}

function Test-StartupReady {
    try {
        $task = Get-ScheduledTask -TaskName $StartupTaskName -ErrorAction SilentlyContinue
        if ($null -ne $task) {
            return $true
        }
    }
    catch {
    }

    foreach ($path in $OldStartupItems) {
        if (Test-Path -LiteralPath $path) {
            return $true
        }
    }

    try {
        $task = Get-ScheduledTask -TaskName "CmccAutoLogin" -ErrorAction SilentlyContinue
        return ($null -ne $task)
    }
    catch {
        return $false
    }
}

function Write-StatusLine {
    param(
        [string]$Label,
        [bool]$Ready,
        [string]$ReadyText,
        [string]$MissingText
    )

    Write-Host ("- " + $Label + ": ") -NoNewline
    if ($Ready) {
        Write-Host "[OK] " -NoNewline -ForegroundColor Green
        Write-Host $ReadyText
    }
    else {
        Write-Host "[--] " -NoNewline -ForegroundColor Yellow
        Write-Host $MissingText
    }
}

function Update-WindowTitle {
    $Host.UI.RawUI.WindowTitle = "CMCC 自动登录"
}

function Show-StatusSummary {
    Update-WindowTitle
    Write-Host "当前状态"
    Write-StatusLine "账号配置" (Test-ConfigReady) "已设置" "未设置"
    Write-StatusLine "开机自启动" (Test-StartupReady) "已启用" "未启用"
    Write-StatusLine "最近日志" (Test-Path -LiteralPath $LogFile) "已有日志" "暂无日志"
}

function Show-Status {
    Show-StatusSummary
    Write-Host ""
    Write-Host ("配置文件位置: " + $ConfigFile)
    if (Test-Path -LiteralPath $ConfigFile) {
        try {
            $config = Get-Content -Raw -LiteralPath $ConfigFile | ConvertFrom-Json
            if ([string]::IsNullOrWhiteSpace($config.UserName) -or [string]::IsNullOrWhiteSpace($config.ProtectedPassword)) {
                Write-Host "配置文件不完整，缺少账号或密码。"
            }
            else {
                Write-Host "配置文件正常。"
                Write-Host ("账号: " + $config.UserName)
            }
        }
        catch {
            Write-Host "配置文件无法读取，请重新设置账号密码。"
        }
    }
    else {
        Write-Host "配置文件不存在，请先设置账号密码。"
    }

    Write-Host ""
    Write-Host ("自启动计划任务: " + $StartupTaskName)
    if (Test-StartupReady) {
        Write-Host "自启动状态: 已启用"
    }
    else {
        Write-Host "自启动状态: 未启用"
    }

    Write-Host ""
    Write-Host ("日志文件位置: " + $LogFile)
    if (Test-Path -LiteralPath $LogFile) {
        Write-Host "最近日志:"
        Get-Content -LiteralPath $LogFile -Tail 8
    }
    else {
        Write-Host "暂无日志"
    }
}

$didInitialSetupCheck = $false

while ($true) {
    if (-not $didInitialSetupCheck) {
        $didInitialSetupCheck = $true
        if (-not (Test-ConfigReady)) {
            Clear-Host
            Update-WindowTitle
            Write-Host "CMCC 自动登录管理"
            Write-Host ""
            $exitCode = Start-AccountSetup
            if ($exitCode -eq 10) {
                continue
            }
            if ($exitCode -eq 0) {
                Write-Host ""
                Write-Host "按回车进入功能菜单..."
                Read-Host | Out-Null
                continue
            }

            Write-Host ""
            Write-Host ("账号密码设置未完成。退出码: " + $exitCode) -ForegroundColor Yellow
            Write-Host "请查看上方提示：如果是密码错误，请重新输入；如果是网络检测失败，请确认当前连接的是未登录的校园网。"
            Write-Host ""
            Write-Host "按回车继续..."
            Read-Host | Out-Null
        }
    }

    Clear-Host
    Update-WindowTitle
    Write-Host "CMCC 自动登录管理"
    Write-Host ""
    Show-StatusSummary
    Write-Host ""
    Write-Host "1. 首次设置/更改账号密码"
    Write-Host "2. 添加到开机自启动"
    Write-Host "3. 立即运行一次登录"
    Write-Host "4. 取消开机自启动"
    Write-Host "5. 查看配置状态和日志位置"
    Write-Host "0. 退出"
    Write-Host ""

    $choice = Read-Host "请选择"
    Write-Host ""
    $returnToMenuImmediately = $false

    switch ($choice) {
        "1" {
            $exitCode = Start-AccountSetup
            if ($exitCode -eq 10) {
                $returnToMenuImmediately = $true
            }
        }
        "2" {
            Invoke-Tool (Join-Path $ScriptDir "install_scheduled_task.ps1") | Out-Null
            $returnToMenuImmediately = $true
        }
        "3" {
            $exitCode = Invoke-Tool (Join-Path $ScriptDir "AutoLogin.ps1") @("-Quiet")
            if ($exitCode -eq 0) {
                Write-Host "当前已经可以上网，或本次登录已成功。" -ForegroundColor Green
                Write-Host "提示：Windows 右下角网络图标可能会延迟 1-2 秒才更新。"
                Start-Sleep -Seconds 2
            }
            else {
                Write-Host "本次登录未成功，请查看上方提示或日志。" -ForegroundColor Yellow
                if ($exitCode -eq 3) {
                    Write-Host "当前没有账号密码配置，请先选择 1 设置账号密码。"
                }
                elseif ($exitCode -eq 1) {
                    Write-Host "可能是账号密码错误或认证页面异常，请选择 1 重新设置账号密码。"
                }
            }
        }
        "4" {
            Invoke-Tool (Join-Path $ScriptDir "uninstall_scheduled_task.ps1") | Out-Null
            $returnToMenuImmediately = $true
        }
        "5" {
            Show-Status
        }
        "0" {
            exit 0
        }
        default {
            Write-Host "无效选择。"
        }
    }

    if ($returnToMenuImmediately) {
        continue
    }

    Write-Host ""
    Write-Host "按回车继续..."
    Read-Host | Out-Null
}
