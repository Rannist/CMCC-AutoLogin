param(
    [switch]$Setup,
    [switch]$Quiet,
    [switch]$StartupNotify,
    [string]$SetupUserName,
    [string]$SetupPassword
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

New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

function Get-Text {
    param([string]$Base64)
    [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($Base64))
}

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
        Write-AppLog "Another login process is already running. Skip duplicate login request."
        exit 8
    }
}

function Release-LoginLock {
    if ($script:LoginMutexAcquired -and $script:LoginMutex) {
        try {
            $script:LoginMutex.ReleaseMutex() | Out-Null
        }
        catch {
            Write-AppLog ("Failed to release login lock: " + $_.Exception.Message)
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
        Write-AppLog ("Failed to read settings: " + $_.Exception.Message)
        return [ordered]@{}
    }
}

function Save-AppSettings {
    param($Settings)

    try {
        $Settings | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $SettingsFile -Encoding UTF8
    }
    catch {
        Write-AppLog ("Failed to save settings: " + $_.Exception.Message)
    }
}

function Reset-StartupOnlineCount {
    $settings = Get-AppSettings
    $settings["startup_online_count"] = 0
    Save-AppSettings $settings
}

function Remove-StartupShortcuts {
    $taskName = "CMCCAutoLogin"
    $startupDir = [Environment]::GetFolderPath("Startup")
    $paths = @(
        (Join-Path $startupDir "AutoLogin.lnk"),
        (Join-Path $startupDir "CmccAutoLogin.lnk"),
        (Join-Path $startupDir "CmccAutoLogin.cmd"),
        (Join-Path $startupDir "CMCC_AutoLogin.lnk")
    )

    $removed = $false

    $null = & schtasks.exe /Query /TN $taskName 2>$null
    if ($LASTEXITCODE -eq 0) {
        $null = & schtasks.exe /Delete /TN $taskName /F 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-AppLog "Startup task removed: $taskName"
            $removed = $true
        }
    }

    foreach ($path in $paths) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
            Write-AppLog "Startup item removed: $path"
            $removed = $true
        }
    }

    return $removed
}

function Show-MessageBox {
    param(
        [string]$Text,
        [string]$Title,
        [string]$Buttons = "OK",
        [string]$Icon = "Information"
    )

    Add-Type -AssemblyName System.Windows.Forms
    return [System.Windows.Forms.MessageBox]::Show($Text, $Title, $Buttons, $Icon)
}

function Show-StartupLoginSuccess {
    [void](Show-MessageBox -Text "校园网已自动登录成功，网络已连接。" -Title "登录成功" -Buttons "OK" -Icon "Information")
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
    Write-AppLog "Startup already-online count: $count"

    if ($count -ge 5) {
        $choice = Show-MessageBox -Text "已连续 5 次开机时检测到网络已连接。`r`n`r`n如果你已经不需要校园网自动登录，是否关闭开机自启？" -Title "是否关闭开机自启" -Buttons "YesNo" -Icon "Question"
        if ($choice -eq [System.Windows.Forms.DialogResult]::Yes) {
            if (Remove-StartupShortcuts) {
                Write-AppLog "Startup auto login disabled by user after already-online reminder."
            }
            $settings = Get-AppSettings
            $settings["startup_online_count"] = 0
            Save-AppSettings $settings
        }
        else {
            Reset-StartupOnlineCount
        }
    }
}

function Convert-SecureStringToPlainText {
    param([securestring]$SecureString)

    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
    try {
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        if ($bstr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
}

function Read-PlainTextPassword {
    param([string]$Encrypted)

    try {
        $secure = ConvertTo-SecureString $Encrypted
        Convert-SecureStringToPlainText $secure
    } catch {
        try {
            [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Encrypted))
        } catch {
            Write-AppLog "Failed to decrypt password"
            throw
        }
    }
}

function Save-ConfigFile {
    param(
        [string]$UserName,
        [string]$EncryptedPassword
    )

    $existingCreatedAt = $null
    if (Test-Path -LiteralPath $ConfigFile) {
        try {
            $existingCreatedAt = (Get-Content -Raw -LiteralPath $ConfigFile | ConvertFrom-Json).CreatedAt
        }
        catch {
            $existingCreatedAt = $null
        }
    }

    [pscustomobject]@{
        UserName = $UserName
        ProtectedPassword = $EncryptedPassword
        PasswordFormat = "dpapi"
        CreatedAt = $(if ($existingCreatedAt) { $existingCreatedAt } else { (Get-Date).ToString("s") })
        UpdatedAt = (Get-Date).ToString("s")
        CredentialVerified = $false
        CredentialVerifiedAt = ""
    } | ConvertTo-Json | Set-Content -LiteralPath $ConfigFile -Encoding UTF8

    Write-AppLog "Config saved: $ConfigFile"
}

function Save-Config {
    if ([string]::IsNullOrWhiteSpace($SetupUserName) -or [string]::IsNullOrWhiteSpace($SetupPassword)) {
        exit 21
    }

    if (-not (Test-Credentials -UserName $SetupUserName -Password $SetupPassword)) {
        exit 20
    }

    $securePassword = ConvertTo-SecureString $SetupPassword -AsPlainText -Force
    $encryptedPassword = ConvertFrom-SecureString $securePassword
    Save-ConfigFile -UserName $SetupUserName -EncryptedPassword $encryptedPassword
}

function Test-ConfigComplete {
    param($Config)

    if ($null -eq $Config) {
        return $false
    }
    if ([string]::IsNullOrWhiteSpace($Config.UserName)) {
        return $false
    }
    if ([string]::IsNullOrWhiteSpace($Config.ProtectedPassword)) {
        return $false
    }
    return $true
}

function Get-Config {
    if ($Quiet -and -not $Setup -and -not (Test-Path -LiteralPath $ConfigFile)) {
        Write-AppLog "Startup login skipped: config is missing account or password."
        exit 3
    }

    if ($Setup -or -not (Test-Path -LiteralPath $ConfigFile)) {
        Save-Config
    }

    $config = Get-Content -Raw -LiteralPath $ConfigFile | ConvertFrom-Json
    if (-not (Test-ConfigComplete $config)) {
        if ($Quiet -and -not $Setup) {
            Write-AppLog "Startup login skipped: config is missing account or password."
            exit 3
        }
        Write-AppLog "Config is missing account or password. Asking user to save credentials."
        Save-Config
        $config = Get-Content -Raw -LiteralPath $ConfigFile | ConvertFrom-Json
    }

    $config
}

function Get-LoginUrl {
    if (Test-Path -LiteralPath $UrlFile) {
        $url = (Get-Content -Raw -LiteralPath $UrlFile -Encoding UTF8).Trim()
        if ($url.StartsWith("http")) {
            return $url
        }
        Write-AppLog "Stored login_url.txt is invalid. No built-in portal URL will be used."
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

function Save-LoginUrl {
    param([string]$Url)

    if (Test-CmccPortalUrl $Url) {
        try {
            Set-Content -LiteralPath $UrlFile -Value $Url -Encoding UTF8
            Write-AppLog "Saved successful login URL: $Url"
        }
        catch {
            Write-AppLog ("Failed to save detected login URL: " + $_.Exception.Message)
        }
    }
}

function Test-NetworkLinkAvailable {
    try {
        return [System.Net.NetworkInformation.NetworkInterface]::GetIsNetworkAvailable()
    }
    catch {
        return $true
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
                Write-AppLog "Detected portal URL from redirect: $location"
                return $location
            }
        }
        catch {
            $response = $_.Exception.Response
            if ($response) {
                $location = $response.Headers["Location"]
                if (Test-CmccPortalUrl $location) {
                    Write-AppLog "Detected portal URL from redirect: $location"
                    return $location
                }
                try {
                    if (Test-CmccPortalUrl $response.ResponseUri.AbsoluteUri) {
                        $detectedUrl = $response.ResponseUri.AbsoluteUri
                        Write-AppLog "Detected portal URL from response URI: $detectedUrl"
                        return $detectedUrl
                    }
                }
                catch {
                }
            }
        }

        try {
            $response = Invoke-WebRequest -Uri $probeUrl -UseBasicParsing -TimeoutSec 2
            if (Test-CmccPortalUrl $response.BaseResponse.ResponseUri.AbsoluteUri) {
                $detectedUrl = $response.BaseResponse.ResponseUri.AbsoluteUri
                Write-AppLog "Detected portal URL from final URI: $detectedUrl"
                return $detectedUrl
            }
            if ($response.Content -match '(?i)(<form\b|password|login|portal|auth|认证|登录|登陆)') {
                $detectedUrl = $response.BaseResponse.ResponseUri.AbsoluteUri
                if (Test-CmccPortalUrl $detectedUrl) {
                    Write-AppLog "Detected portal content, using final URI: $detectedUrl"
                    return $detectedUrl
                }
            }
        }
        catch {
            Write-AppLog ("Portal auto-detect failed for $probeUrl`: " + $_.Exception.Message)
        }
    }

    $cachedUrl = Get-LoginUrl
    if (-not [string]::IsNullOrWhiteSpace($cachedUrl)) {
        Write-AppLog "Use cached successful login URL: $cachedUrl"
        return $cachedUrl
    }
    Write-AppLog "Portal auto-detect did not find a CMCC login URL and no cached successful URL exists."
    return $null
}

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutMilliseconds = 600
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
            if ($uri.Scheme -eq "https") {
                $port = 443
            }
            else {
                $port = 80
            }
        }

        $reachable = Test-TcpPort -HostName $uri.Host -Port $port
        if (-not $reachable) {
            Write-AppLog "Portal host is not reachable quickly: $($uri.Host):$port"
        }
        return $reachable
    }
    catch {
        Write-AppLog ("Portal reachability check failed: " + $_.Exception.Message)
        return $false
    }
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
    $fields
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

function Invoke-CmccLogin {
    param(
        [string]$LoginUrl,
        [string]$UserName,
        [string]$Password
    )

    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $openTimeout = 12
    $postTimeout = 15
    if ($StartupNotify -and -not $Setup) {
        $openTimeout = 6
        $postTimeout = 8
    }

    Write-AppLog "Open portal: $LoginUrl"
    $outer = Invoke-WebRequest -Uri $LoginUrl -WebSession $session -UseBasicParsing -TimeoutSec $openTimeout
    $outerHtml = $outer.Content
    $innerUrl = $LoginUrl
    $innerHtml = $outerHtml

    $frameMatch = [regex]::Match($outerHtml, "(?is)<frame\b[^>]*name\s*=\s*[`"']mainFrame[`"'][^>]*src\s*=\s*[`"']([^`"']+)[`"']")
    if (-not $frameMatch.Success) {
        $frameMatch = [regex]::Match($outerHtml, "(?is)<frame\b[^>]*src\s*=\s*[`"']([^`"']*index\.jsp[^`"']*)[`"']")
    }
    if ($frameMatch.Success) {
        $innerUrl = Get-AbsoluteUrl $LoginUrl $frameMatch.Groups[1].Value
        Write-AppLog "Open login form: $innerUrl"
        $inner = Invoke-WebRequest -Uri $innerUrl -WebSession $session -UseBasicParsing -TimeoutSec $openTimeout
        $innerHtml = $inner.Content
    }
    else {
        Write-AppLog "Use portal page as login form."
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
    Write-AppLog "Post login: $postUrl"
    $response = Invoke-WebRequest -Uri $postUrl -Method Post -Body $fields -WebSession $session -UseBasicParsing -TimeoutSec $postTimeout

    Write-AppLog ("Login response: HTTP {0}, {1} bytes" -f [int]$response.StatusCode, $response.RawContentLength)
    try {
        Write-AppLog ("Login response URI: " + $response.BaseResponse.ResponseUri.AbsoluteUri)
    }
    catch {
    }
    return $response.Content
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

function Test-GenericLoginFailureContent {
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
        [int]$TimeoutSeconds = 5,
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

function Test-Credentials {
    param(
        [string]$UserName,
        [string]$Password
    )

    $loginUrl = Find-LoginUrl
    if ([string]::IsNullOrWhiteSpace($loginUrl)) {
        Write-AppLog 'Credential check skipped: login portal URL was not detected and no cached successful URL exists.'
        return $false
    }
    if (-not (Test-LoginUrlReachable -LoginUrl $loginUrl)) {
        Write-AppLog 'Credential check skipped: login portal is not reachable.'
        return $false
    }

    try {
        $content = Invoke-CmccLogin -LoginUrl $loginUrl -UserName $UserName -Password $Password
        if (Test-LoginSuccessContent $content) {
            Write-AppLog ("Credential check passed by portal success response: " + (Get-ResponseTextSummary $content))
            Save-LoginUrl $loginUrl
            return $true
        }
        if (Test-LoginFailureContent $content) {
            Write-AppLog 'Credential check failed: portal returned a login failure message.'
            if (-not $Quiet) {
                Write-Host "账号或密码错误，请重新输入密码。" -ForegroundColor Yellow
            }
            return $false
        }
        if (Test-GenericLoginFailureContent $content) {
            Write-AppLog 'Credential check failed: portal returned a generic login failure message.'
            Write-AppLog ("Credential check response summary: " + (Get-ResponseTextSummary $content))
            if (-not $Quiet) {
                Write-Host "认证站返回登录失败，不能确认是账号密码错误，请稍后重试。" -ForegroundColor Yellow
            }
            return $false
        }

        if (-not $Quiet) {
            Write-Host "已提交登录请求，正在等待联网确认..."
        }
        if (Wait-Internet -TimeoutSeconds 12 -IntervalSeconds 1) {
            Write-AppLog 'Credential check passed.'
            if (-not $Quiet) {
                Write-Host "联网确认成功，账号密码已通过验证。" -ForegroundColor Green
            }
            return $true
        }

        Write-AppLog 'Credential check failed: internet access was not confirmed after waiting.'
        if (-not $Quiet) {
            Write-Host "没有检测到联网成功，本次账号密码不会保存。" -ForegroundColor Yellow
        }
        return $false
    }
    catch {
        if (Test-Internet) {
            Write-AppLog 'Credential check skipped because internet is already available.'
            return $true
        }

        Write-AppLog ("Credential check error: " + $_.Exception.Message)
        return $false
    }
}

try {
    Acquire-LoginLock

    if (-not (Test-NetworkLinkAvailable)) {
        Write-AppLog 'No network link is available. Skip login quickly.'
        exit 4
    }

    if ($Setup -and (Test-Internet)) {
        Write-AppLog 'Internet is already available. Skip account setup.'
        exit 10
    }

    if (-not $Setup) {
        if (Test-Internet) {
            Write-AppLog 'Internet is already available. Skip login.'
            if ($StartupNotify) {
                Update-StartupOnlineCount
            }
            exit 0
        }

        if ($StartupNotify) {
            Reset-StartupOnlineCount
        }
    }

    $config = Get-Config
    if ($Setup) {
        Write-AppLog 'Setup completed.'
        exit 0
    }

    if ($StartupNotify) {
        $loginUrl = Find-LoginUrl
        Write-AppLog "Startup fast path uses detected or cached login URL: $loginUrl"
    }
    else {
        $loginUrl = Find-LoginUrl
    }
    if ([string]::IsNullOrWhiteSpace($loginUrl)) {
        Write-AppLog 'Login portal URL was not detected and no cached successful URL exists. Skip login quickly.'
        exit 4
    }
    if (-not (Test-LoginUrlReachable -LoginUrl $loginUrl)) {
        Write-AppLog 'Login portal is not reachable. Skip login quickly.'
        exit 4
    }

    $password = Read-PlainTextPassword $config.ProtectedPassword
    $genericFailure = $false

    try {
        $content = Invoke-CmccLogin -LoginUrl $loginUrl -UserName $config.UserName -Password $password
        if (Test-LoginSuccessContent $content) {
            Write-AppLog ("Portal returned login success response: " + (Get-ResponseTextSummary $content))
            Save-LoginUrl $loginUrl
            exit 0
        }
        if (Test-LoginFailureContent $content) {
            if (-not $Quiet) {
                Write-Host "账号或密码错误，请选择 1 重新设置账号密码。" -ForegroundColor Yellow
            }
            throw "账号或密码错误。"
        }
        if (Test-GenericLoginFailureContent $content) {
            $genericFailure = $true
            Write-AppLog ("Portal returned generic failure before internet check: " + (Get-ResponseTextSummary $content))
        }
    }
    finally {
        $password = $null
    }

    Write-AppLog 'Wait for internet after login.'
    $waitSeconds = 12
    if ($StartupNotify) {
        $waitSeconds = 8
    }
    if ($genericFailure) {
        $waitSeconds = 30
    }
    if (Wait-Internet -TimeoutSeconds $waitSeconds -IntervalSeconds 1) {
        Write-AppLog 'Internet check passed.'
        Save-LoginUrl $loginUrl
        if ($StartupNotify) {
            Reset-StartupOnlineCount
            Show-StartupLoginSuccess
        }
        exit 0
    }

    Write-AppLog 'Internet check did not pass. Login may still have succeeded if this test URL is blocked.'
    exit 2
}
catch {
    Write-AppLog ("ERROR: " + $_.Exception.Message)
    if (-not $Quiet) {
        Write-Host ""
        Write-Host "按回车退出。"
        Read-Host | Out-Null
    }
    exit 1
}
finally {
    Release-LoginLock
}
