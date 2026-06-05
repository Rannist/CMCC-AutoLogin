CMCC 校园网自动登录
=====================

这是一个校园网自动登录工具。主程序负责账号配置、状态查看、手动登录和开机自启管理；开机自启使用独立快速脚本，不打开主程序窗口。

功能特点
--------
- 校园网自动登录。
- 当前用户计划任务开机自启，无需管理员权限。
- 开机自启通过 scripts/StartupAutoLogin.vbs 无窗口启动 scripts/StartupAutoLogin.ps1 -StartupNotify。
- 登录进度、成功、错误、重试、取消等提示统一使用自定义卡片窗口，不使用 Windows 原生 MessageBox。
- 账号密码使用 Windows DPAPI 加密保存到 config.json，并维护 PasswordFormat / CredentialVerified / CredentialVerifiedAt 状态。
- 保存或修改账号后会重置为未验证；只有真实提交账号密码并确认联网成功后才标记为已验证。
- 开机自启会检测 WLAN/网络、认证站、系统代理、账号配置。
- 代理开启、认证站不可达、网络未就绪时提供重试；取消后自动打开主程序。
- 账号缺失、账号为空、明确账号密码错误或通用异常时，确认后自动打开主程序。

首次使用
--------
1. 双击 CMCC_AutoLogin.exe。
2. 输入校园网账号和密码。
3. 点击“保存账号”。
4. 未联网时点击“立即登录/验证登录”，确认账号密码能成功联网。
5. 点击“开机自启”。
6. 如果主程序显示“需修复”，点击“修复自启”即可重装正确的计划任务。

开机自启说明
------------
- 计划任务名称：CMCCAutoLogin。
- 自启方式：当前用户 Windows 计划任务。
- 自启脚本：scripts/StartupAutoLogin.vbs，内部无窗口启动 scripts/StartupAutoLogin.ps1 -StartupNotify。
- 不生成 AutoLogin.lnk 快捷方式。
- 不主动打开主程序窗口，除非发生需要用户处理的问题。
- 连续 5 次开机时已经联网，会询问是否关闭自启。
- 如果旧版本升级后计划任务仍指向根目录脚本，主程序会显示“需修复”，点击按钮会重新安装正确路径。

提示窗口
--------
- 发布包内的提示程序位于 notifier/StartupNotifier.exe，使用目录模式打包以减少冷启动延迟。
- 主程序和开机自启提示都使用该自定义窗口。
- 开机自启开始时会先显示“正在准备自动登录”，后续登录成功或失败会更新同一个窗口，避免登录完成后才慢弹提示。
- 登录成功：用户点击“确定”后提示程序和自启脚本退出。
- 可重试问题：显示“重试/取消”，取消后自动打开主程序。
- 错误问题：用户点击“确定”后自动打开主程序。

主要文件
--------
- CMCC_AutoLogin.exe：主程序。
- notifier/StartupNotifier.exe：自定义提示窗口。
- scripts/StartupAutoLogin.vbs：开机自启无窗口启动器。
- scripts/StartupAutoLogin.ps1：开机自启快速登录脚本。
- scripts/AutoLogin.ps1：手动登录和账号验证脚本。
- scripts/install_scheduled_task.ps1：安装开机自启计划任务。
- scripts/uninstall_scheduled_task.ps1：卸载开机自启计划任务。
- scripts/manage.ps1：命令行管理菜单。
- login_url.txt：运行时自动生成的认证地址缓存；发布包默认不携带，程序登录成功并确认联网后会保存本次成功使用的认证地址。
- config.json：账号密码和验证状态。
- settings.json：窗口设置和自启提醒计数。

发布包隐私
----------
build_release.py 生成发布包时不会复制本机 config.json、settings.json 或 login_url.txt。

发布包内会生成：
- 空白 config.json：UserName 和 ProtectedPassword 为空，PasswordFormat 为 dpapi，CredentialVerified 为 false。
- 默认 settings.json。

login_url.txt 不会随发布包打包。程序会优先自动探测当前认证地址，不再限定固定 CMCC 认证域名；只有登录成功并确认联网后，才会在程序目录生成并更新 login_url.txt。探测失败时只会使用上一次登录成功缓存的地址；如果没有缓存，程序会提示重新探测或打开主程序，不再使用内置固定认证地址。

适用前提：
- Windows 10/11。
- 已连接到 CMCC 或同类校园网 Wi-Fi。
- 校园网通过普通 Web Portal 输入账号密码认证。
- 认证流程兼容 /authServlet，并使用 UserName / PassWord 字段提交。
- 认证页不要求验证码、短信、二维码或复杂前端加密。
- 系统代理、VPN 或抓包代理应关闭，避免拦截认证请求。

不适用或需要单独适配：
- 802.1X、企业网关、客户端拨号类认证。
- 验证码、短信、二维码、人脸或动态口令登录。
- 登录参数需要浏览器 JavaScript 加密后再提交。
- 认证接口不是 /authServlet，或字段名完全不同。
- 学校限制共享账号、绑定设备、限制同时在线设备数。

如果页面结构不同，需要提供诊断信息后单独适配脚本。

项目根目录里的本机配置和日志不会被删除。

常见问题
--------
1. 开机提示代理开启  
   关闭系统代理后点“重试”。代理可能拦截校园网认证请求。

2. 开机提示账号密码错误，但手动登录成功  
   新版本会优先自动探测当前认证地址，并且只有认证站明确返回账号/密码错误文本时才提示账号密码错误。请确认使用的是本 README 同目录下的新版本程序。

3. 开机没有自动登录  
   确认 WLAN 已打开、已连接 CMCC 校园网，并检查计划任务 CMCCAutoLogin 是否存在。主程序显示“需修复”时，点击“修复自启”重装计划任务。

4. 已联网时无法验证账号  
   已联网时无法通过认证站真实验证账号密码。程序只保存账号密码并保持未验证，下次需要认证时会自动验证。

5. 不确定哪里出问题  
   在主程序“操作日志”区域点击“诊断”，程序会检查网络、代理、认证站、账号配置、验证状态、计划任务路径、通知程序和脚本文件。若 scripts 目录缺少必需脚本，程序会优先从内置备份或旧根目录脚本自动补全；仍无法补全时再提示重新解压完整发布包。点击“复制诊断”可复制结果用于反馈。

打包方式
--------
推荐在项目根目录运行：

python build_release.py

输出：
- dist/CMCC_AutoLogin.exe
- dist/notifier/StartupNotifier.exe
- dist/scripts/
- CMCC_AutoLogin.zip

