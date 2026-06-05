# CMCC AutoLogin

CMCC AutoLogin 是一个 Windows 校园网自动登录工具。主程序用于保存账号、手动登录、查看状态和管理开机自启；开机自启使用独立 PowerShell 脚本和自定义提示窗口，不打开主程序界面。

## 下载使用

普通用户不要下载源码包，直接到 GitHub Releases 下载 `CMCC_AutoLogin.zip`。

1. 下载并解压 `CMCC_AutoLogin.zip`。
2. 双击 `CMCC_AutoLogin.exe`。
3. 输入校园网账号和密码并保存。
4. 未联网时点击“立即登录/验证登录”，确认可以成功认证。
5. 需要开机自动登录时，点击“开机自启”。

## 适用前提

本项目只适合以下认证环境：

- Windows 10/11。
- 校园网通过普通 Web Portal 输入账号密码认证。
- 认证流程与 CMCC 或同类校园网相近。
- 认证提交接口兼容 `/authServlet`。
- 账号和密码字段兼容 `UserName`、`PassWord`。
- 认证页不要求验证码、短信、二维码或复杂前端加密。
- 使用前需要先连接到对应校园网 Wi-Fi，例如 CMCC 校园网。
- 系统代理、VPN 或抓包代理应关闭，避免拦截认证请求。

## 不适用或需要单独适配

以下场景通常不能直接使用：

- 802.1X、企业网关、客户端拨号类认证。
- 验证码、短信、二维码、人脸或动态口令登录。
- 登录参数需要浏览器 JavaScript 加密后再提交。
- 认证接口不是 `/authServlet`，或字段名完全不同。
- 学校限制共享账号、绑定设备、限制同时在线设备数。

如果页面结构不同，需要提供诊断信息后单独适配脚本。

## 隐私说明

- 发布包不会携带作者本机账号、密码、日志或历史认证地址。
- 用户账号密码保存在本机 `config.json`。
- 密码使用 Windows DPAPI 加密，正常情况下只能由当前 Windows 用户解密。
- `login_url.txt` 只在用户本机登录成功并确认联网后生成，用于缓存上次成功认证地址。

## 主要功能

- 校园网手动登录和验证。
- 当前用户计划任务开机自启，无需管理员权限。
- 开机自启通过 `scripts/StartupAutoLogin.vbs` 无窗口启动 `scripts/StartupAutoLogin.ps1 -StartupNotify`。
- 登录进度、成功、错误和重试提示使用 `notifier/StartupNotifier.exe` 自定义窗口。
- 主程序可检测网络、代理、账号状态、计划任务路径和必要脚本文件。

## 源码构建

源码构建需要 Windows、Python 3.11 或兼容版本，以及依赖：

```powershell
pip install -r requirements.txt
python build_release.py
```

输出文件：

- `dist/CMCC_AutoLogin.exe`
- `dist/notifier/StartupNotifier.exe`
- `dist/scripts/`
- `CMCC_AutoLogin.zip`

发布前应确认 ZIP 内不包含个人 `config.json`、`login_url.txt`、日志或调试文件。
