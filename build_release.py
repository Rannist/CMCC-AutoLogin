# -*- coding: utf-8 -*-
import json
import os
import shutil
import subprocess
import zipfile


APP_NAME = "CMCC_AutoLogin"
NOTIFIER_NAME = "StartupNotifier"
ZIP_NAME = "CMCC_AutoLogin.zip"
SCRIPT_FILES = [
    "AutoLogin.ps1",
    "StartupAutoLogin.ps1",
    "StartupAutoLogin.vbs",
    "manage.ps1",
    "install_scheduled_task.ps1",
    "uninstall_scheduled_task.ps1",
]


def project_dir():
    return os.path.dirname(os.path.abspath(__file__))


def pyinstaller_path():
    return shutil.which("pyinstaller") or "pyinstaller"


def remove_path(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)


def cleanup_generated_artifacts(script_dir, keep_dist=True):
    for name in ("build", "__pycache__"):
        remove_path(os.path.join(script_dir, name))
    for name in ("AutoLogin.zip", "AutoLogin.spec", "CMCC_AutoLogin.spec", "StartupNotifier.spec"):
        remove_path(os.path.join(script_dir, name))
    if not keep_dist:
        remove_path(os.path.join(script_dir, "dist"))


def run_pyinstaller(command, script_dir, label):
    result = subprocess.run(command, capture_output=True, text=True, cwd=script_dir)
    if result.returncode != 0:
        print(f"{label} 打包失败:")
        print(result.stderr)
        return False
    print(f"{label} 打包成功")
    return True


def build_exe():
    script_dir = project_dir()
    os.chdir(script_dir)
    cleanup_generated_artifacts(script_dir, keep_dist=False)

    assets_dir = os.path.join(script_dir, "assets")
    icon_path = os.path.join(assets_dir, "app_icon.ico")
    pyinstaller = pyinstaller_path()

    main_cmd = [
        pyinstaller,
        "--onefile",
        "--windowed",
        "--name",
        APP_NAME,
        "--collect-all=PIL",
    ]
    if os.path.exists(icon_path):
        main_cmd.extend(["--icon", icon_path])
    if os.path.exists(assets_dir):
        main_cmd.extend(["--add-data", f"{assets_dir};assets"])
    for name in SCRIPT_FILES:
        src = os.path.join(script_dir, name)
        if os.path.exists(src):
            main_cmd.extend(["--add-data", f"{src};bundled_scripts"])
    main_cmd.append("CMCC_AutoLogin.py")

    if not run_pyinstaller(main_cmd, script_dir, "主程序 EXE"):
        return False

    notifier_cmd = [
        pyinstaller,
        "--onedir",
        "--windowed",
        "--name",
        NOTIFIER_NAME,
    ]
    if os.path.exists(icon_path):
        notifier_cmd.extend(["--icon", icon_path])
    notifier_cmd.append("StartupNotifier.py")

    return run_pyinstaller(notifier_cmd, script_dir, "通知程序 EXE")


def write_release_templates(dist_dir):
    config = {
        "UserName": "",
        "ProtectedPassword": "",
        "PasswordFormat": "dpapi",
        "CreatedTime": json.dumps({"__type": "DateTime", "iso": "2024-01-01T00:00:00Z"}),
        "CredentialVerified": False,
        "CredentialVerifiedAt": "",
    }
    settings = {
        "window_width": 620,
        "window_height": 860,
        "first_run_completed": False,
        "startup_online_count": 0,
    }
    with open(os.path.join(dist_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    with open(os.path.join(dist_dir, "settings.json"), "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    remove_path(os.path.join(dist_dir, "login_url.txt"))
    print("生成发布模板: config.json, settings.json")


def copy_release_files(script_dir, dist_dir):
    notifier_dir = os.path.join(dist_dir, "notifier")
    scripts_dir = os.path.join(dist_dir, "scripts")
    os.makedirs(scripts_dir, exist_ok=True)

    notifier_root = os.path.join(dist_dir, f"{NOTIFIER_NAME}.exe")
    if os.path.exists(notifier_root):
        os.makedirs(notifier_dir, exist_ok=True)
        shutil.move(notifier_root, os.path.join(notifier_dir, f"{NOTIFIER_NAME}.exe"))
        print("移动文件: notifier/StartupNotifier.exe")

    notifier_dir_root = os.path.join(dist_dir, NOTIFIER_NAME)
    if os.path.isdir(notifier_dir_root):
        remove_path(notifier_dir)
        shutil.move(notifier_dir_root, notifier_dir)
        print("移动目录: notifier")

    root_files = [
        "README.txt",
    ]
    script_files = SCRIPT_FILES
    for name in root_files:
        src = os.path.join(script_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dist_dir, name))
            print(f"复制文件: {name}")

    for name in script_files:
        src = os.path.join(script_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(scripts_dir, name))
            print(f"复制文件: scripts/{name}")

    write_release_templates(dist_dir)
    return root_files, script_files


def create_zip():
    script_dir = project_dir()
    dist_dir = os.path.join(script_dir, "dist")
    zip_path = os.path.join(script_dir, ZIP_NAME)
    root_files, script_files = copy_release_files(script_dir, dist_dir)

    remove_path(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        package_files = [
            (os.path.join(dist_dir, f"{APP_NAME}.exe"), f"{APP_NAME}.exe"),
            (os.path.join(dist_dir, "config.json"), "config.json"),
            (os.path.join(dist_dir, "settings.json"), "settings.json"),
        ]
        package_files.extend((os.path.join(dist_dir, name), name) for name in root_files)
        package_files.extend((os.path.join(dist_dir, "scripts", name), f"scripts/{name}") for name in script_files)

        for src, arcname in package_files:
            if os.path.exists(src):
                zf.write(src, arcname)
                print(f"添加文件: {arcname}")

        notifier_dir = os.path.join(dist_dir, "notifier")
        if os.path.exists(notifier_dir):
            for root, _, files in os.walk(notifier_dir):
                for name in files:
                    src = os.path.join(root, name)
                    arcname = os.path.relpath(src, dist_dir)
                    zf.write(src, arcname)
                    print(f"添加文件: {arcname}")

    print(f"ZIP 已创建: {zip_path}")
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("CMCC 校园网自动登录 - 构建脚本")
    print("=" * 50)

    if build_exe() and create_zip():
        cleanup_generated_artifacts(project_dir(), keep_dist=True)
        print("\n构建完成")
        print(f"EXE: {os.path.join(project_dir(), 'dist', APP_NAME + '.exe')}")
        print(f"ZIP: {os.path.join(project_dir(), ZIP_NAME)}")
    else:
        print("构建失败")
