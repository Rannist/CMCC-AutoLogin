param(
    [switch]$StartupNotify
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = $ScriptDir
if ((Split-Path -Leaf $ScriptDir) -ieq "scripts") {
    $AppDir = Split-Path -Parent $ScriptDir
}
$ConfigFile = Join-Path $AppDir "config.json"
$SettingsFile = Join-Path $AppDir "settings.json"
$LogFile = Join-Path $AppDir "autologin.log"
$UrlFile = Join-Path $AppDir "login_url.txt"
$MainExeFile = Join-Path $AppDir "CMCC_AutoLogin.exe"
$NotifierFile = Join-Path (Join-Path $AppDir "notifier") "StartupNotifier.exe"
$LegacyNotifierFile = Join-Path (Join-Path $AppDir "internal") "StartupNotifier.exe"
$LegacyNotifierOnedirFile = Join-Path (Join-Path (Join-Path $AppDir "internal") "StartupNotifier") "StartupNotifier.exe"
$NoticeStateFile = Join-Path $env:TEMP "CMCCAutoLogin_notice_state.json"
$NoticeResponseFile = Join-Path $env:TEMP "CMCCAutoLogin_notice_response.json"
$NoticeProcessStarted = $false

function Write-AppLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

$LoginMutex = $null
$LoginMutexAcquired = $false

function Acquire-LoginLock {
    $script:LoginMutex = New-Object System.Threading.Mutex($false, "Local\CMCCAutoLogin.Login")
    $script:LoginMutexAcquired = $script:LoginMutex.WaitOne(0)
    if (-not $script:LoginMutexAcquired) {
        Write-AppLog "Startup fast login skipped: another login process is already running."
        if ($StartupNotify) {
            $null = Show-StartupNotice -Title "校园网自动登录" -Text "已有登录任务正在运行，本次开机登录已跳过。" -Kind "warning" -Buttons "ok"
        }
        exit 8
    }
}

function Release-LoginLock {
    if ($script:LoginMutexAcquired -and $script:LoginMutex) {
        try {
            $script:LoginMutex.ReleaseMutex() | Out-Null
        }
        catch {
            Write-AppLog ("Startup login lock release failed: " + $_.Exception.Message)
        }
    }
    if ($script:LoginMutex) {
        $script:LoginMutex.Dispose()
    }
}

function Get-AppSettings {
    if (-not (Test-Path -LiteralPath $SettingsFile)) {
        return [ordered]@{}
    }
    try {
        $raw = Get-Content -Raw -LiteralPath $SettingsFile -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($raw)) {
            return [ordered]@{}
        }
        $settings = $raw | ConvertFrom-Json
        $result = [ordered]@{}
        foreach ($property in $settings.PSObject.Properties) {
            $result[$property.Name] = $property.Value
        }
        return $result
    }
    catch {
        Write-AppLog ("Startup settings read failed: " + $_.Exception.Message)
        return [ordered]@{}
    }
}

function Save-AppSettings {
    param($Settings)
    try {
        $Settings | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $SettingsFile -Encoding UTF8
    }
    catch {
        Write-AppLog ("Startup settings save failed: " + $_.Exception.Message)
    }
}

function Save-Config {
    param($Config)

    try {
        $Config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ConfigFile -Encoding UTF8
    }
    catch {
        Write-AppLog ("Startup config save failed: " + $_.Exception.Message)
    }
}

function Set-CredentialVerified {
    param(
        $Config,
        [string]$PlainPassword = ""
    )

    if ($null -eq $Config) {
        return
    }
    if ([string]::IsNullOrWhiteSpace($Config.UserName) -or [string]::IsNullOrWhiteSpace($Config.ProtectedPassword)) {
        return
    }

    if ($Config.PasswordFormat -ne "dpapi" -and -not [string]::IsNullOrWhiteSpace($PlainPassword)) {
        try {
            $securePassword = ConvertTo-SecureString $PlainPassword -AsPlainText -Force
            $Config | Add-Member -NotePropertyName "ProtectedPassword" -NotePropertyValue (ConvertFrom-SecureString $securePassword) -Force
            $Config | Add-Member -NotePropertyName "PasswordFormat" -NotePropertyValue "dpapi" -Force
            Write-AppLog "Startup migrated stored password to DPAPI format."
        }
        catch {
            Write-AppLog ("Startup password migration failed: " + $_.Exception.Message)
        }
    }
    else {
        $Config | Add-Member -NotePropertyName "PasswordFormat" -NotePropertyValue "dpapi" -Force
    }
    $Config | Add-Member -NotePropertyName "CredentialVerified" -NotePropertyValue $true -Force
    $Config | Add-Member -NotePropertyName "CredentialVerifiedAt" -NotePropertyValue (Get-Date -Format "s") -Force
    Save-Config $Config
    Write-AppLog "Startup fast login marked credentials as verified."
}

function Reset-StartupOnlineCount {
    $settings = Get-AppSettings
    $settings["startup_online_count"] = 0
    Save-AppSettings $settings
}

function Show-StartupNotice {
    param(
        [string]$Title,
        [string]$Text,
        [string]$Kind = "warning",
        [string]$Buttons = "ok"
    )

    if (-not $StartupNotify) {
        return 0
    }

    if ($NoticeProcessStarted -and (Test-Path -LiteralPath $NoticeStateFile)) {
        $state = [pscustomobject]@{
            title = $Title
            message = $Text
            kind = $Kind
            buttons = $Buttons
        }
        $state | ConvertTo-Json -Compress | Set-Content -LiteralPath $NoticeStateFile -Encoding UTF8

        if ($Kind -eq "success" -or $Buttons -eq "none") {
            return 0
        }

        Remove-Item -LiteralPath $NoticeResponseFile -Force -ErrorAction SilentlyContinue
        while (-not (Test-Path -LiteralPath $NoticeResponseFile)) {
            Start-Sleep -Milliseconds 120
        }
        try {
            $response = Get-Content -Raw -LiteralPath $NoticeResponseFile -Encoding UTF8 | ConvertFrom-Json
            return [int]$response.exit_code
        }
        catch {
            return 20
        }
    }

    $activeNotifier = $NotifierFile
    if (-not (Test-Path -LiteralPath $activeNotifier) -and (Test-Path -LiteralPath $LegacyNotifierOnedirFile)) {
        $activeNotifier = $LegacyNotifierOnedirFile
    }
    if (-not (Test-Path -LiteralPath $activeNotifier) -and (Test-Path -LiteralPath $LegacyNotifierFile)) {
        $activeNotifier = $LegacyNotifierFile
    }
    if (-not (Test-Path -LiteralPath $activeNotifier)) {
        Write-AppLog "Startup notifier is missing: $activeNotifier"
        if ($Kind -eq "success") {
            return 0
        }
        return 20
    }

    $payload = [pscustomobject]@{
        title = $Title
        message = $Text
        kind = $Kind
        buttons = $Buttons
    } | ConvertTo-Json -Compress
    $payloadBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload))
    $result = Start-Process -FilePath $activeNotifier -ArgumentList @("--payload", $payloadBase64) -WorkingDirectory $AppDir -Wait -PassThru

    return $result.ExitCode
}

function Start-StartupProgressNotice {
    if (-not $StartupNotify) {
        return
    }

    $activeNotifier = $NotifierFile
    if (-not (Test-Path -LiteralPath $activeNotifier) -and (Test-Path -LiteralPath $LegacyNotifierOnedirFile)) {
        $activeNotifier = $LegacyNotifierOnedirFile
    }
    if (-not (Test-Path -LiteralPath $activeNotifier) -and (Test-Path -LiteralPath $LegacyNotifierFile)) {
        $activeNotifier = $LegacyNotifierFile
    }
    if (-not (Test-Path -LiteralPath $activeNotifier)) {
        Write-AppLog "Startup progress notifier is missing: $activeNotifier"
        return
    }

    Remove-Item -LiteralPath $NoticeResponseFile -Force -ErrorAction SilentlyContinue
    $state = [pscustomobject]@{
        title = "校园网自动登录"
        message = "正在准备自动登录，请稍候..."
        kind = "warning"
        buttons = "none"
        state_file = $NoticeStateFile
        response_file = $NoticeResponseFile
    }
    $state | ConvertTo-Json -Compress | Set-Content -LiteralPath $NoticeStateFile -Encoding UTF8
    $payloadBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($state | ConvertTo-Json -Compress)))
    Start-Process -FilePath $activeNotifier -ArgumentList @("--payload", $payloadBase64) -WorkingDirectory $AppDir | Out-Null
    $script:NoticeProcessStarted = $true
}

function Test-NoticeRetry {
    param($Code)

    try {
        return ([int]$Code -eq 10)
    }
    catch {
        return $false
    }
}

function Remove-StartupTask {
    $taskName = "CMCCAutoLogin"
    $null = & schtasks.exe /Query /TN $taskName 2>$null
    if ($LASTEXITCODE -eq 0) {
        $null = & schtasks.exe /Delete /TN $taskName /F 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-AppLog "Startup task removed: $taskName"
            return $true
        }
    }
    return $false
}

function Update-StartupOnlineCount {
    $settings = Get-AppSettings
    $count = 0
    if ($settings.Contains("startup_online_count")) {
        try {
            $count = [int]$settings["startup_online_count"]
        }
        catch {
            $count = 0
        }
    }

    $count += 1
    $settings["startup_online_count"] = $count
    Save-AppSettings $settings
    Write-AppLog "Startup fast login already-online count: $count"

    if ($count -ge 5) {
        $choice = Show-StartupNotice -Title "是否关闭开机自启" -Text "已连续 5 次开机时检测到网络已连接。`r`n`r`n如果你已经不需要校园网自动登录，可以关闭开机自启。" -Kind "warning" -Buttons "yes-no"
        if ([int]$choice -eq 0) {
            $null = Remove-StartupTask
        }
        Reset-StartupOnlineCount
    }
}

function Show-StartupLoginSuccess {
    $null = Show-StartupNotice -Title "登录成功" -Text "校园网已自动登录成功，网络已连接。" -Kind "success" -Buttons "ok"
}

function Show-StartupProblem {
    param(
        [string]$Text,
        [string]$Buttons = "ok",
        [string]$Kind = "warning"
    )

    return (Show-StartupNotice -Title "校园网自动登录提示" -Text $Text -Kind $Kind -Buttons $Buttons)
}

function Open-MainProgram {
    try {
        if (Test-Path -LiteralPath $MainExeFile) {
            Start-Process -FilePath $MainExeFile -WorkingDirectory $AppDir | Out-Null
            Write-AppLog "Opened main program: $MainExeFile"
        }
        else {
            Write-AppLog "Main program not found: $MainExeFile"
        }
    }
    catch {
        Write-AppLog ("Failed to open main program: " + $_.Exception.Message)
    }
}

function Show-ProblemAndOpenMain {
    param([string]$Text)

    $null = Show-StartupProblem -Text $Text -Buttons "ok" -Kind "error"
    Open-MainProgram
}

function Save-LoginUrl {
    param([string]$Url)

    if (Test-CmccPortalUrl $Url) {
        try {
            Set-Content -LiteralPath $UrlFile -Value $Url -Encoding UTF8
            Write-AppLog "Startup saved successful login URL: $Url"
        }
        catch {
            Write-AppLog ("Startup failed to save detected login URL: " + $_.Exception.Message)
        }
    }
}

function Test-ProxyEnabled {
    try {
        $proxy = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" -ErrorAction Stop
        if ($proxy.ProxyEnable -eq 1 -and -not [string]::IsNullOrWhiteSpace($proxy.ProxyServer)) {
            Write-AppLog "Startup proxy detected: ProxyServer=$($proxy.ProxyServer)"
            return $true
        }
        if (-not [string]::IsNullOrWhiteSpace($proxy.AutoConfigURL)) {
            Write-AppLog "Startup proxy detected: AutoConfigURL=$($proxy.AutoConfigURL)"
            return $true
        }
    }
    catch {
        Write-AppLog ("Startup proxy check failed: " + $_.Exception.Message)
    }
    return $false
}

function Test-NetworkLinkAvailable {
    try {
        return [System.Net.NetworkInformation.NetworkInterface]::GetIsNetworkAvailable()
    }
    catch {
        return $true
    }
}

function Wait-NetworkLink {
    param(
        [int]$TimeoutSeconds = 12,
        [int]$IntervalSeconds = 1
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-NetworkLinkAvailable) {
            return $true
        }
        if ((Get-Date) -lt $deadline) {
            Start-Sleep -Seconds $IntervalSeconds
        }
    } while ((Get-Date) -lt $deadline)

    return (Test-NetworkLinkAvailable)
}

function Test-Internet {
    $checks = @(
        @{ Url = "http://www.msftconnecttest.com/connecttest.txt"; Pattern = "Microsoft Connect Test"; Status = 200 },
        @{ Url = "http://connectivitycheck.gstatic.com/generate_204"; Pattern = ""; Status = 204 },
        @{ Url = "http://captive.apple.com/hotspot-detect.html"; Pattern = "Success"; Status = 200 }
    )

    foreach ($check in $checks) {
        try {
            $response = Invoke-WebRequest -Uri $check.Url -UseBasicParsing -TimeoutSec 2
            $finalUrl = $response.BaseResponse.ResponseUri.AbsoluteUri
            if (Test-CmccPortalUrl $finalUrl) {
                continue
            }
            if ([int]$response.StatusCode -ne [int]$check.Status) {
                continue
            }
            if (-not [string]::IsNullOrWhiteSpace($check.Pattern) -and $response.Content -notmatch $check.Pattern) {
                continue
            }
            return $true
        }
        catch {
        }
    }
    return $false
}

function Wait-Internet {
    param(
        [int]$TimeoutSeconds = 4,
        [int]$IntervalSeconds = 1
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-Internet) {
            return $true
        }
        if ((Get-Date) -lt $deadline) {
            Start-Sleep -Seconds $IntervalSeconds
        }
    } while ((Get-Date) -lt $deadline)

    return (Test-Internet)
}

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutMilliseconds = 500
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $asyncResult = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $asyncResult.AsyncWaitHandle.WaitOne($TimeoutMilliseconds, $false)) {
            return $false
        }
        $client.EndConnect($asyncResult)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Test-LoginUrlReachable {
    param([string]$LoginUrl)

    try {
        $uri = [Uri]$LoginUrl
        $port = $uri.Port
        if ($uri.IsDefaultPort) {
            $port = $(if ($uri.Scheme -eq "https") { 443 } else { 80 })
        }
        return (Test-TcpPort -HostName $uri.Host -Port $port)
    }
    catch {
        Write-AppLog ("Startup portal reachability check failed: " + $_.Exception.Message)
        return $false
    }
}

function Read-PlainTextPassword {
    param([string]$Encrypted)

    try {
        $secure = ConvertTo-SecureString $Encrypted
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try {
            return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        }
        finally {
            if ($bstr -ne [IntPtr]::Zero) {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
            }
        }
    }
    catch {
        return [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Encrypted))
    }
}

function Get-LoginUrl {
    if (Test-Path -LiteralPath $UrlFile) {
        $url = (Get-Content -Raw -LiteralPath $UrlFile -Encoding UTF8).Trim()
        if ($url.StartsWith("http")) {
            return $url
        }
        Write-AppLog "Startup stored login_url.txt is invalid. No built-in portal URL will be used."
    }
    return $null
}

function Test-CmccPortalUrl {
    param([string]$Url)

    if ([string]::IsNullOrWhiteSpace($Url)) {
        return $false
    }
    try {
        $uri = [Uri]$Url
        if ($uri.Scheme -ne "http" -and $uri.Scheme -ne "https") {
            return $false
        }
        if ([string]::IsNullOrWhiteSpace($uri.Host)) {
            return $false
        }
        return ($uri.Host -notmatch '(^|\.)msftconnecttest\.com$|(^|\.)gstatic\.com$|(^|\.)google\.com$|(^|\.)apple\.com$|(^|\.)neverssl\.com$|(^|\.)connectivitycheck\.gstatic\.com$')
    }
    catch {
        return $false
    }
}

function Find-LoginUrl {
    $probeUrls = @(
        "http://www.msftconnecttest.com/connecttest.txt",
        "http://connectivitycheck.gstatic.com/generate_204",
        "http://captive.apple.com/hotspot-detect.html",
        "http://neverssl.com/"
    )

    foreach ($probeUrl in $probeUrls) {
        try {
            $response = Invoke-WebRequest -Uri $probeUrl -UseBasicParsing -TimeoutSec 2 -MaximumRedirection 0
            $location = $response.Headers["Location"]
            if (Test-CmccPortalUrl $location) {
                Write-AppLog "Startup detected portal URL from redirect: $location"
                return $location
            }
        }
        catch {
            $response = $_.Exception.Response
            if ($response) {
                try {
                    $location = $response.Headers["Location"]
                    if (Test-CmccPortalUrl $location) {
                        Write-AppLog "Startup detected portal URL from redirect: $location"
                        return $location
                    }
                }
                catch {
                    Write-AppLog ("Startup redirect header read failed: " + $_.Exception.Message)
                }
                try {
                    if (Test-CmccPortalUrl $response.ResponseUri.AbsoluteUri) {
                        $detectedUrl = $response.ResponseUri.AbsoluteUri
                        Write-AppLog "Startup detected portal URL from response URI: $detectedUrl"
                        return $detectedUrl
                    }
                }
                catch {
                    Write-AppLog ("Startup response URI read failed: " + $_.Exception.Message)
                }
            }
        }

        try {
            $response = Invoke-WebRequest -Uri $probeUrl -UseBasicParsing -TimeoutSec 2
            if (Test-CmccPortalUrl $response.BaseResponse.ResponseUri.AbsoluteUri) {
                $detectedUrl = $response.BaseResponse.ResponseUri.AbsoluteUri
                Write-AppLog "Startup detected portal URL from final URI: $detectedUrl"
                return $detectedUrl
            }
            if ($response.Content -match '(?i)(<form\b|password|login|portal|auth|认证|登录|登陆)') {
                $detectedUrl = $response.BaseResponse.ResponseUri.AbsoluteUri
                if (Test-CmccPortalUrl $detectedUrl) {
                    Write-AppLog "Startup detected portal content, using final URI: $detectedUrl"
                    return $detectedUrl
                }
            }
        }
        catch {
            Write-AppLog ("Startup portal final-URI detection failed for $probeUrl`: " + $_.Exception.Message)
        }
    }

    $cachedUrl = Get-LoginUrl
    if (-not [string]::IsNullOrWhiteSpace($cachedUrl)) {
        Write-AppLog "Startup uses cached successful login URL: $cachedUrl"
        return $cachedUrl
    }
    Write-AppLog "Startup portal auto-detect did not find a CMCC login URL and no cached successful URL exists."
    return $null
}

function Get-Config {
    if (-not (Test-Path -LiteralPath $ConfigFile)) {
        Write-AppLog "Startup fast login skipped: config is missing."
        Show-ProblemAndOpenMain "开机自动登录未执行：未保存账号密码。`r`n`r`n点击“确定”后将自动打开主程序，请先保存账号密码并验证登录。"
        exit 3
    }
    $config = Get-Content -Raw -LiteralPath $ConfigFile -Encoding UTF8 | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace($config.UserName) -or [string]::IsNullOrWhiteSpace($config.ProtectedPassword)) {
        Write-AppLog "Startup fast login skipped: account or password is missing."
        Show-ProblemAndOpenMain "开机自动登录未执行：账号或密码为空。`r`n`r`n点击“确定”后将自动打开主程序，请保存完整账号密码后再使用开机自启。"
        exit 3
    }
    return $config
}

function Test-LoginFailureContent {
    param([string]$Content)

    if ([string]::IsNullOrWhiteSpace($Content)) {
        return $false
    }

    $normalized = $Content.Trim()
    if ($normalized -eq "0") {
        return $true
    }

    return ($Content -match '(?i)(密码错误|密码不正确|账号.*密码.*错误|用户名.*密码.*错误|用户不存在|password[^<]{0,40}(wrong|error|incorrect)|invalid[^<]{0,40}password)')
}

function Test-GenericPortalFailureContent {
    param([string]$Content)

    if ([string]::IsNullOrWhiteSpace($Content)) {
        return $false
    }

    return ($Content -match '(?i)(认证失败|登录失败|登陆失败|login\s*failed|auth[^<]{0,40}fail)')
}

function Test-LoginSuccessContent {
    param([string]$Content)

    if ([string]::IsNullOrWhiteSpace($Content)) {
        return $false
    }

    return ($Content -match '(?i)(登录成功|登陆成功|认证成功|通过上网认证|已通过.*认证|successfully\s+login|login\s+success)')
}

function Get-ResponseTextSummary {
    param([string]$Content)

    if ([string]::IsNullOrWhiteSpace($Content)) {
        return ""
    }

    $text = $Content -replace '(?is)<script\b.*?</script>', ' '
    $text = $text -replace '(?is)<style\b.*?</style>', ' '
    $text = $text -replace '(?is)<[^>]+>', ' '
    $text = $text -replace '&nbsp;', ' '
    $text = $text -replace '\s+', ' '
    $text = $text.Trim()
    if ($text.Length -gt 180) {
        return $text.Substring(0, 180)
    }
    return $text
}

function Get-AbsoluteUrl {
    param(
        [string]$BaseUrl,
        [string]$RelativeUrl
    )
    ([Uri]::new([Uri]$BaseUrl, $RelativeUrl)).AbsoluteUri
}

function Get-BrowserHeaders {
    param([string]$RefererUrl = "")

    $headers = @{
        "Accept" = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        "Accept-Language" = "zh-CN,zh;q=0.9,en;q=0.8"
        "Cache-Control" = "no-cache"
        "Pragma" = "no-cache"
    }
    if (-not [string]::IsNullOrWhiteSpace($RefererUrl)) {
        $headers["Referer"] = $RefererUrl
    }
    return $headers
}

function Get-PostHeaders {
    param([string]$RefererUrl)

    $headers = Get-BrowserHeaders -RefererUrl $RefererUrl
    try {
        $uri = [Uri]$RefererUrl
        $headers["Origin"] = "{0}://{1}" -f $uri.Scheme, $uri.Authority
    }
    catch {
    }
    return $headers
}

function Get-HtmlAttribute {
    param(
        [string]$Tag,
        [string]$Name
    )

    $pattern = "(?i)\b" + [regex]::Escape($Name) + "\s*=\s*([`"'])(.*?)\1"
    $match = [regex]::Match($Tag, $pattern)
    if ($match.Success) {
        [System.Net.WebUtility]::HtmlDecode($match.Groups[2].Value)
    }
}

function Get-HiddenInputs {
    param([string]$Html)

    $fields = @{}
    foreach ($match in [regex]::Matches($Html, "(?is)<input\b[^>]*>")) {
        $tag = $match.Value
        $type = Get-HtmlAttribute $tag "type"
        if ($type -and $type.ToLowerInvariant() -ne "hidden") {
            continue
        }
        $name = Get-HtmlAttribute $tag "name"
        if ([string]::IsNullOrWhiteSpace($name)) {
            continue
        }
        $fields[$name] = (Get-HtmlAttribute $tag "value")
        if ($null -eq $fields[$name]) {
            $fields[$name] = ""
        }
    }
    return $fields
}

function Get-FirstFormHtml {
    param([string]$Html)

    $match = [regex]::Match($Html, "(?is)<form\b[^>]*>.*?</form>")
    if ($match.Success) {
        return $match.Value
    }
    return ""
}

function Get-FormAction {
    param([string]$FormHtml)

    if ([string]::IsNullOrWhiteSpace($FormHtml)) {
        return $null
    }
    $tag = [regex]::Match($FormHtml, "(?is)<form\b[^>]*>").Value
    if ([string]::IsNullOrWhiteSpace($tag)) {
        return $null
    }
    return (Get-HtmlAttribute $tag "action")
}

function Get-InputNameByPattern {
    param(
        [string]$Html,
        [string]$TypePattern,
        [string]$NamePattern
    )

    foreach ($match in [regex]::Matches($Html, "(?is)<input\b[^>]*>")) {
        $tag = $match.Value
        $type = Get-HtmlAttribute $tag "type"
        if ([string]::IsNullOrWhiteSpace($type)) {
            $type = "text"
        }
        if (-not [string]::IsNullOrWhiteSpace($TypePattern) -and $type -notmatch $TypePattern) {
            continue
        }
        $name = Get-HtmlAttribute $tag "name"
        if ([string]::IsNullOrWhiteSpace($name)) {
            continue
        }
        $id = Get-HtmlAttribute $tag "id"
        $probe = "$name $id"
        if ($probe -match $NamePattern) {
            return $name
        }
    }
    return $null
}

function Invoke-FastLogin {
    param(
        [string]$LoginUrl,
        [string]$UserName,
        [string]$Password
    )

    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Write-AppLog "Startup fast login open portal: $LoginUrl"
    $outer = Invoke-WebRequest -Uri $LoginUrl -WebSession $session -UseBasicParsing -TimeoutSec 4
    $outerHtml = $outer.Content
    $innerUrl = $LoginUrl
    $innerHtml = $outerHtml

    $frameMatch = [regex]::Match($outerHtml, "(?is)<frame\b[^>]*name\s*=\s*[`"']mainFrame[`"'][^>]*src\s*=\s*[`"']([^`"']+)[`"']")
    if (-not $frameMatch.Success) {
        $frameMatch = [regex]::Match($outerHtml, "(?is)<frame\b[^>]*src\s*=\s*[`"']([^`"']*index\.jsp[^`"']*)[`"']")
    }
    if ($frameMatch.Success) {
        $innerUrl = Get-AbsoluteUrl $LoginUrl $frameMatch.Groups[1].Value
        Write-AppLog "Startup fast login open form: $innerUrl"
        $inner = Invoke-WebRequest -Uri $innerUrl -WebSession $session -UseBasicParsing -TimeoutSec 4
        $innerHtml = $inner.Content
    }

    $fields = Get-HiddenInputs $innerHtml
    $fields["UserName"] = $UserName
    $fields["PassWord"] = $Password
    $fields["cookie"] = "0"
    if ($fields.ContainsKey("isCookie")) {
        $fields["isCookie"] = "false"
    }
    if ($fields.ContainsKey("cookieType")) {
        $fields["cookieType"] = "-1"
    }

    $postUrl = Get-AbsoluteUrl $innerUrl "/authServlet"
    Write-AppLog "Startup fast login post: $postUrl"
    $response = Invoke-WebRequest -Uri $postUrl -Method Post -Body $fields -WebSession $session -UseBasicParsing -TimeoutSec 6
    Write-AppLog ("Startup fast login response: HTTP {0}, {1} bytes" -f [int]$response.StatusCode, $response.RawContentLength)
    try {
        Write-AppLog ("Startup fast login response URI: " + $response.BaseResponse.ResponseUri.AbsoluteUri)
    }
    catch {
    }
    return $response.Content
}

function Invoke-CachedFastLoginFirst {
    param(
        $Config,
        [string]$CachedLoginUrl
    )

    if ([string]::IsNullOrWhiteSpace($CachedLoginUrl)) {
        return $false
    }
    if (-not (Test-LoginUrlReachable -LoginUrl $CachedLoginUrl)) {
        Write-AppLog "Startup cached fast path skipped: cached portal is not reachable."
        return $false
    }

    $password = Read-PlainTextPassword $Config.ProtectedPassword
    $passwordForMigration = $password
    try {
        Write-AppLog "Startup cached fast path uses cached login URL: $CachedLoginUrl"
        $content = Invoke-FastLogin -LoginUrl $CachedLoginUrl -UserName $Config.UserName -Password $password
        if (Test-LoginSuccessContent $content) {
            Write-AppLog ("Startup cached fast path got portal success response: " + (Get-ResponseTextSummary $content))
            Save-LoginUrl $CachedLoginUrl
            Set-CredentialVerified -Config $Config -PlainPassword $passwordForMigration
            if ($StartupNotify) {
                Reset-StartupOnlineCount
                Show-StartupLoginSuccess
            }
            return $true
        }

        if (Test-LoginFailureContent $content) {
            Write-AppLog "Startup cached fast path got strict account/password failure content; fallback to current portal detection before final decision."
            return $false
        }

        if (Wait-Internet -TimeoutSeconds 3 -IntervalSeconds 1) {
            Write-AppLog "Startup cached fast path passed internet check."
            Save-LoginUrl $CachedLoginUrl
            Set-CredentialVerified -Config $Config -PlainPassword $passwordForMigration
            if ($StartupNotify) {
                Reset-StartupOnlineCount
                Show-StartupLoginSuccess
            }
            return $true
        }

        Write-AppLog "Startup cached fast path did not confirm internet; fallback to normal detection."
        return $false
    }
    catch {
        Write-AppLog ("Startup cached fast path failed: " + $_.Exception.Message)
        return $false
    }
    finally {
        $password = $null
    }
}

try {
    Write-AppLog "Startup fast login started."
    Acquire-LoginLock

    if (-not (Wait-NetworkLink -TimeoutSeconds 6 -IntervalSeconds 1)) {
        Start-StartupProgressNotice
        Write-AppLog "Startup fast login skipped: no network link."
        $choice = Show-StartupProblem -Text "开机自动登录未执行：当前没有可用网络连接。`r`n`r`n请检查 WLAN 开关是否打开，并确认已连接 CMCC 校园网。点击“重试”会再次尝试；点击“取消”会自动打开主程序。" -Buttons "retry-cancel"
        if (Test-NoticeRetry $choice) {
            Write-AppLog "User chose retry after no network link."
            & $PSCommandPath -StartupNotify
            exit $LASTEXITCODE
        }
        Open-MainProgram
        exit 4
    }

    while (Test-ProxyEnabled) {
        Start-StartupProgressNotice
        $choice = Show-StartupProblem -Text "检测到系统代理已开启，可能导致校园网开机自动登录失败。`r`n`r`n请先关闭代理，然后点击“重试”。如果需要修改账号或检查配置，请点击“取消”，程序会自动打开主界面。" -Buttons "retry-cancel"
        if (Test-NoticeRetry $choice) {
            Write-AppLog "User chose retry after proxy warning."
            Start-Sleep -Seconds 1
            continue
        }
        Write-AppLog "Startup login cancelled because proxy is enabled."
        Open-MainProgram
        exit 6
    }

    $config = Get-Config
    $cachedLoginUrl = Get-LoginUrl
    if (Invoke-CachedFastLoginFirst -Config $config -CachedLoginUrl $cachedLoginUrl) {
        exit 0
    }

    Start-StartupProgressNotice
    $null = Show-StartupNotice -Title "校园网自动登录" -Text "正在检查网络和代理状态..." -Kind "warning" -Buttons "none"

    if (Test-Internet) {
        Write-AppLog "Startup fast login skipped: internet is already available."
        if ($StartupNotify) {
            Update-StartupOnlineCount
        }
        exit 0
    }
    if ($StartupNotify) {
        Reset-StartupOnlineCount
    }

    $null = Show-StartupNotice -Title "校园网自动登录" -Text "正在探测校园网认证地址..." -Kind "warning" -Buttons "none"
    $loginUrl = Find-LoginUrl
    if ([string]::IsNullOrWhiteSpace($loginUrl)) {
        Write-AppLog "Startup fast login skipped: portal URL was not detected and no cached successful URL exists."
        $choice = Show-StartupProblem -Text "开机自动登录未执行：没有获取到校园网认证地址。`r`n`r`n请确认 WLAN 已打开并连接 CMCC 校园网。点击“重试”会重新探测；点击“取消”会自动打开主程序。" -Buttons "retry-cancel"
        if (Test-NoticeRetry $choice) {
            Write-AppLog "User chose retry after portal URL missing."
            & $PSCommandPath -StartupNotify
            exit $LASTEXITCODE
        }
        Open-MainProgram
        exit 4
    }
    if (-not (Test-LoginUrlReachable -LoginUrl $loginUrl)) {
        Write-AppLog "Startup fast login skipped: portal is not reachable quickly."
        $choice = Show-StartupProblem -Text "开机自动登录未执行：认证站暂时不可达。`r`n`r`n常见原因：WLAN 未打开、未连接 CMCC 校园网、代理开启、刚开机无线网络还没连上。点击“重试”会再次尝试；点击“取消”会自动打开主程序。" -Buttons "retry-cancel"
        if (Test-NoticeRetry $choice) {
            Write-AppLog "User chose retry after portal unreachable."
            & $PSCommandPath -StartupNotify
            exit $LASTEXITCODE
        }
        Open-MainProgram
        exit 4
    }

    $password = Read-PlainTextPassword $config.ProtectedPassword
    $passwordForMigration = $password
    $genericFailure = $false
    try {
        $null = Show-StartupNotice -Title "校园网自动登录" -Text "正在提交校园网登录请求..." -Kind "warning" -Buttons "none"
        $content = Invoke-FastLogin -LoginUrl $loginUrl -UserName $config.UserName -Password $password
        if (Test-LoginSuccessContent $content) {
            Write-AppLog ("Startup fast login got portal success response: " + (Get-ResponseTextSummary $content))
            Save-LoginUrl $loginUrl
            Set-CredentialVerified -Config $config -PlainPassword $passwordForMigration
            $passwordForMigration = $null
            if ($StartupNotify) {
                Reset-StartupOnlineCount
                Show-StartupLoginSuccess
            }
            exit 0
        }
        if (Test-LoginFailureContent $content) {
            Write-AppLog "Startup fast login got strict account/password failure content. Try detecting current portal URL once before final failure."
            $detectedLoginUrl = Find-LoginUrl
            if (-not [string]::IsNullOrWhiteSpace($detectedLoginUrl) -and $detectedLoginUrl -ne $loginUrl) {
                Write-AppLog "Startup retry uses detected portal URL: $detectedLoginUrl"
                $content = Invoke-FastLogin -LoginUrl $detectedLoginUrl -UserName $config.UserName -Password $password
            }
            if (Test-LoginFailureContent $content) {
                Write-AppLog "Startup fast login failed: portal returned account or password error."
                Show-ProblemAndOpenMain "开机自动登录失败：账号或密码错误。`r`n`r`n点击“确定”后将自动打开主程序，请修改账号密码并重新验证登录。"
                exit 5
            }
        }
        if (Test-GenericPortalFailureContent $content) {
            $genericFailure = $true
            Write-AppLog ("Startup fast login got generic portal failure before internet check: " + (Get-ResponseTextSummary $content))
        }
    }
    finally {
        $password = $null
    }

    $null = Show-StartupNotice -Title "校园网自动登录" -Text "登录请求已提交，正在确认联网状态..." -Kind "warning" -Buttons "none"
    $waitSeconds = 5
    if ($genericFailure) {
        $waitSeconds = 25
    }
    if (Wait-Internet -TimeoutSeconds $waitSeconds -IntervalSeconds 1) {
        Write-AppLog "Startup fast login passed internet check."
        Save-LoginUrl $loginUrl
        Set-CredentialVerified -Config $config -PlainPassword $passwordForMigration
        $passwordForMigration = $null
        if ($StartupNotify) {
            Reset-StartupOnlineCount
            Show-StartupLoginSuccess
        }
        exit 0
    }

    Write-AppLog "Startup fast login submitted, but internet check did not pass immediately."
    $choice = Show-StartupProblem -Text "开机自动登录已提交，但没有确认联网成功。`r`n`r`n请检查 WLAN、CMCC 校园网和代理状态。点击“重试”会再次尝试；点击“取消”会自动打开主程序。" -Buttons "retry-cancel"
    if (Test-NoticeRetry $choice) {
        Write-AppLog "User chose retry after unconfirmed startup login."
        & $PSCommandPath -StartupNotify
        exit $LASTEXITCODE
    }
    Open-MainProgram
    exit 2
}
catch {
    Write-AppLog ("Startup fast login ERROR: " + $_.Exception.Message)
    Show-ProblemAndOpenMain ("开机自动登录失败：`r`n" + $_.Exception.Message + "`r`n`r`n点击确定后将自动打开主程序，请检查 WLAN、CMCC 校园网、代理和账号配置。")
    exit 1
}
finally {
    Release-LoginLock
}










