"""
MMS-Main - Build Script
Packaging: PyInstaller single-directory mode (--onedir)
Builds both 主程序 and Web 查询服务
"""
import os
import sys
import shutil
import subprocess

# 从 config.py 读取版本号
CLIENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CLIENT_DIR)
from config import APP_VERSION

PROJECT_ROOT = os.path.dirname(CLIENT_DIR)

# 工程名称与版本号
APP_NAME = "MMS-Main"
VERSION = APP_VERSION  # e.g. "v4305"

# 输出目录与 EXE 命名
OUTPUT_DIR_NAME = f"{APP_NAME}"
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "dist", OUTPUT_DIR_NAME)
DIST_PATH = os.path.join(PROJECT_ROOT, "dist")

# 主程序 EXE 名
MAIN_EXE_NAME = APP_NAME
# Web 服务 EXE 名
WEB_EXE_NAME = "MMS-WebServices"
UPDATE_EXE_NAME = "MMS-Update"

ICON_PATH = os.path.join(CLIENT_DIR, "Image", "app_icon.ico")

# ---------- 资源文件收集 ----------

def _collect_image_files():
    files = [
        (os.path.join(CLIENT_DIR, "Image", "app_icon.ico"), "Image"),
        (os.path.join(CLIENT_DIR, "Image", "login_banner.png"), "Image"),
        (os.path.join(CLIENT_DIR, "Image", "tcl_logo.png"), "Image"),
    ]
    # version.txt 包含在打包中（位于项目根目录）
    version_txt = os.path.join(PROJECT_ROOT, "version.txt")
    if os.path.isfile(version_txt):
        files.append((version_txt, "."))
    return files


def _collect_web_files():
    """收集 web_ 目录下非 Python 资源文件（templates、static 等）
    Python 模块通过 hidden-import 打包，避免重复
    """
    web_dir = os.path.join(CLIENT_DIR, "web_")
    files = []
    for root, dirs, filenames in os.walk(web_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fname in filenames:
            if fname.endswith(".py") or fname.endswith(".pyc"):
                continue
            src = os.path.join(root, fname)
            rel_dir = os.path.relpath(root, web_dir)
            dst = os.path.join("web_", rel_dir) if rel_dir != "." else "web_"
            files.append((src, dst))
    return files


def _collect_i18n_files():
    """收集 i18n/lang 翻译文件"""
    lang_dir = os.path.join(CLIENT_DIR, "i18n", "lang")
    files = []
    for fname in os.listdir(lang_dir):
        if fname.endswith(".py"):
            files.append((os.path.join(lang_dir, fname), os.path.join("i18n", "lang")))
    return files


def _collect_pyd_files():
    """收集 pyd 目录下的 .pyd 编译模块和 __init__.py"""
    pyd_dir = os.path.join(CLIENT_DIR, "pyd")
    files = []
    for fname in os.listdir(pyd_dir):
        if fname in ("__pycache__", "_build_c"):
            continue
        src = os.path.join(pyd_dir, fname)
        if os.path.isfile(src):
            files.append((src, "pyd"))
    return files


COMMON_DATA_FILES = _collect_image_files() + _collect_i18n_files() + _collect_pyd_files()

# main.py 是 loader，需要从 __pycache__ 加载 main.cpython-311.pyc
# ---------- 通用 hidden imports ----------

COMMON_HIDDEN_IMPORTS = [
    # PySide6 & 核心
    "PySide6.QtXml",
    "keyring",
    # Cython 编译的模块
    "pyd",
    "pyd.app_config",
    "pyd.credential_manager",
    "pyd.mysql_client",
]

WEB_HIDDEN_IMPORTS = [
    # ===== 配置模块（web_ 服务依赖） =====
    "utils.app_config",
    "utils.credential_manager",
    # ===== Web 服务自身模块 =====
    "app",
    "database",
    "schemas",
    "service",
    "routes",
    "routes.query",
    # ===== FastAPI + Uvicorn + Starlette =====
    "fastapi",
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "starlette",
    "starlette.applications",
    "starlette.routing",
    "starlette.requests",
    "starlette.responses",
    "starlette.staticfiles",
    "starlette.status",
    "starlette.middleware",
    "starlette.middleware.cors",
    "starlette.exceptions",
    "pydantic",
    "pydantic.v1",
    "pydantic_core",
    # ===== mDNS =====
    "zeroconf",
    "zeroconf.asyncio",
    "ifaddr",
    # ===== ASGI / HTTP =====
    "h11",
    "httptools",
    # ===== 其他 =====
    "pymysql",
    "pymysql.cursors",
    "keyring",
    "anyio",
    "anyio._backends",
    "sniffio",
    "idna",
    "jinja2",
]


def log(msg: str):
    print(f"  -> {msg}")


def clean():
    log("Cleaning old build files...")
    for spec in [f"{MAIN_EXE_NAME}.spec", f"{WEB_EXE_NAME}.spec", f"{UPDATE_EXE_NAME}.spec"]:
        spec_path = os.path.join(PROJECT_ROOT, spec)
        if os.path.exists(spec_path):
            os.remove(spec_path)
    build_dir = os.path.join(PROJECT_ROOT, "build")
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir, ignore_errors=True)


def _run_pyinstaller(name, entry_point, data_files, hidden_imports, extra_args=None, use_clean=True):
    """执行 PyInstaller 打包（输出到临时目录，避免 --clean 冲突）"""
    tmp_dist = os.path.join(PROJECT_ROOT, "_build_tmp")

    cmd = [
        sys.executable or "python",
        "-m", "PyInstaller",
        "-y",
        "--onedir",
        "--name", name,
        "--distpath", tmp_dist,
        "--icon", ICON_PATH,
        "--log-level", "WARN",
    ]
    if use_clean:
        cmd.append("--clean")

    if extra_args:
        cmd.extend(extra_args)

    for src, dst in data_files:
        cmd.append("--add-data")
        sep = ";" if sys.platform == "win32" else ":"
        cmd.append(f"{src}{sep}{dst}")

    for mod in hidden_imports:
        cmd.append("--hidden-import")
        cmd.append(mod)

    cmd.append(entry_point)
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"\n[ERROR] Build failed for {name}!")
        sys.exit(1)


def build_main_app():
    """打包主程序（--windowed 无控制台）"""
    log(f"Building {MAIN_EXE_NAME}.exe (main app, windowed mode)...")
    _run_pyinstaller(
        name=MAIN_EXE_NAME,
        entry_point=os.path.join(CLIENT_DIR, "main.py"),
        data_files=COMMON_DATA_FILES,
        # 主程序只需要通用依赖，web_ 模块通过独立的 Web 服务 EXE 运行
        hidden_imports=COMMON_HIDDEN_IMPORTS,
        extra_args=[
            "--windowed",
            # 主程序也需要 web_ 目录在搜索路径中（run.py 通过相对路径查找）
        ],
    )


def build_web_service():
    """打包 Web 查询服务（--windowed 无控制台）"""
    log(f"Building {WEB_EXE_NAME}.exe (web service, console mode)...")
    _run_pyinstaller(
        name=WEB_EXE_NAME,
        entry_point=os.path.join(CLIENT_DIR, "web_", "run.py"),
        data_files=_collect_web_files() + _collect_pyd_files(),
        hidden_imports=WEB_HIDDEN_IMPORTS + [
            "pyd",
            "pyd.app_config",
            "pyd.credential_manager",
            "pyd.mysql_client",
        ],
        extra_args=[
            # --windowed removed: need console for uvicorn in frozen mode
            "--paths", os.path.join(CLIENT_DIR, "web_"),
            "--collect-all", "pydantic",
            "--collect-all", "pydantic_core",
            "--collect-all", "fastapi",
            "--collect-all", "starlette",
            "--collect-all", "uvicorn",
        ],
        use_clean=False,
    )



def build_update_exe():
    """Build MMS-Update.exe as a single file (console mode).
    Uses --onefile so it does NOT depend on _internal/ and can replace it freely.
    """
    log(f"Building {UPDATE_EXE_NAME}.exe (standalone updater, single file)...")
    tmp_dist = os.path.join(PROJECT_ROOT, "_build_tmp")
    cmd = [
        sys.executable or "python",
        "-m", "PyInstaller",
        "-y",
        "--onefile",
        "--name", UPDATE_EXE_NAME,
        "--distpath", tmp_dist,
        "--log-level", "WARN",
        "--clean",
        "--workpath", os.path.join(tmp_dist, "MMS-Update_build"),
        "--specpath", os.path.join(PROJECT_ROOT, "_build_tmp"),
    ]
    for mod in [
        "utils.updater",
        "utils.app_config",
        "utils.credential_manager",
        "pyd",
        "pyd.app_config",
        "pyd.credential_manager",
        "pyd.mysql_client",
        "pymysql",
        "psutil",
    ]:
        cmd.append("--hidden-import")
        cmd.append(mod)
    cmd.append(os.path.join(CLIENT_DIR, "MMS-Update.py"))
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"\n[ERROR] Build failed for {UPDATE_EXE_NAME}!")
        sys.exit(1)


def merge_outputs():
    """合并两个打包输出到同一目录（共享 _internal）"""
    log("Merging outputs into single directory...")
    tmp_dist = os.path.join(PROJECT_ROOT, "_build_tmp")
    main_dist_src = os.path.join(tmp_dist, MAIN_EXE_NAME)
    web_dist = os.path.join(tmp_dist, WEB_EXE_NAME)
    main_dist = OUTPUT_DIR  # 最终目标目录

    # 0. 备份用户数据文件
    user_data = {}
    if os.path.isdir(main_dist):
        for fname in {".language.json", "local_cache.db",
                      "config.ini", ".mms_creds.json",
                      ".login_completed.json", ".remember_login.json", ".auto_export.json"}:
            fpath = os.path.join(main_dist, fname)
            if os.path.isfile(fpath):
                user_data[fname] = fpath

    # 1. 将主程序构建目录合并到最终位置
    if os.path.isdir(main_dist_src):
        # 尝试直接重命名（最快速）
        _final_name = main_dist
        _tmp_replace = os.path.join(os.path.dirname(main_dist),
                                   f".merge_tmp_{os.path.basename(main_dist_src)}")
        try:
            if os.path.exists(_tmp_replace):
                shutil.rmtree(_tmp_replace, ignore_errors=True)
            os.replace(main_dist_src, _tmp_replace)
            if os.path.exists(main_dist):
                shutil.rmtree(main_dist, ignore_errors=True)
            os.replace(_tmp_replace, main_dist)
            log(f"  Replaced {MAIN_EXE_NAME}/ -> {OUTPUT_DIR_NAME}/")
        except OSError:
            # 目标目录存在锁定文件（如 local_cache.db*），保留 _tmp_replace，逐文件覆盖
            def _deep_merge(src, dst):
                try:
                    entries = os.listdir(src)
                except FileNotFoundError:
                    return
                for item in entries:
                    s = os.path.join(src, item)
                    d = os.path.join(dst, item)
                    if os.path.isdir(s) and not os.path.islink(s):
                        os.makedirs(d, exist_ok=True)
                        _deep_merge(s, d)
                    else:
                        try:
                            os.replace(s, d)
                        except (PermissionError, OSError):
                            try:
                                shutil.copy2(s, d)
                            except (PermissionError, OSError):
                                log(f'  (skip locked: {os.path.basename(d)})')
                os.makedirs(main_dist, exist_ok=True)
            _deep_merge(_tmp_replace, main_dist)
            log(f'  Copied {MAIN_EXE_NAME}/ -> {OUTPUT_DIR_NAME}/ (locked files preserved)')

    # 3. 把 Web 服务 EXE 复制到主输出目录
    os.makedirs(main_dist, exist_ok=True)
    web_exe = os.path.join(web_dist, f"{WEB_EXE_NAME}.exe")
    if os.path.isfile(web_exe):
        shutil.copy2(web_exe, os.path.join(main_dist, f"{WEB_EXE_NAME}.exe"))
        log(f"  Copied {WEB_EXE_NAME}.exe -> {OUTPUT_DIR_NAME}/")

    # 3b. Copy MMS-Update.exe (--onefile: output is directly in tmp_dist/)
    update_exe = os.path.join(tmp_dist, f"{UPDATE_EXE_NAME}.exe")
    if os.path.isfile(update_exe):
        shutil.copy2(update_exe, os.path.join(main_dist, f"{UPDATE_EXE_NAME}.exe"))
        log(f"  Copied {UPDATE_EXE_NAME}.exe -> {OUTPUT_DIR_NAME}/")

    # 4. 合并 _internal 目录（web 服务所需的 pydantic/fastapi 等模块）
    web_internal = os.path.join(web_dist, "_internal")
    main_internal = os.path.join(main_dist, "_internal")
    if os.path.isdir(web_internal) and os.path.isdir(main_internal):
        for root, dirs, files in os.walk(web_internal):
            rel_root = os.path.relpath(root, web_internal)
            target_root = os.path.join(main_internal, rel_root)
            os.makedirs(target_root, exist_ok=True)
            for fname in files:
                src = os.path.join(root, fname)
                dst = os.path.join(target_root, fname)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
        log("  Merged _internal/ dependencies")

    # 5. Copy version.txt from project root to both _internal/ and root
    src_version = os.path.join(PROJECT_ROOT, "version.txt")
    internal_version = os.path.join(main_dist, "_internal", "version.txt")
    root_version = os.path.join(main_dist, "version.txt")
    if os.path.isfile(src_version):
        if os.path.exists(internal_version):
            os.remove(internal_version)
        shutil.copy2(src_version, internal_version)
        if os.path.exists(root_version):
            os.remove(root_version)
        shutil.copy2(src_version, root_version)
        log("  Copied version.txt -> root + _internal/")
    # 6. Copy Image/ to root (for icon and banner in frozen mode)
    _internal_image = os.path.join(main_dist, "_internal", "Image")
    _root_image = os.path.join(main_dist, "Image")
    if os.path.isdir(_internal_image):
        if os.path.isdir(_root_image):
            shutil.rmtree(_root_image, ignore_errors=True)
        shutil.copytree(_internal_image, _root_image)
        log("  Copied Image/ -> root (for window icon + login banner)")

    # 6. 从项目根目录复制最新的 config.ini（包含 [app] 和 [web_query] 节）
    src_config = os.path.join(PROJECT_ROOT, "config.ini")
    dst_config = os.path.join(main_dist, "config.ini")
    if os.path.isfile(src_config):
        shutil.copy2(src_config, dst_config)
        log("  Copied config.ini -> root")

    # 7. 恢复用户数据文件
    for fname, src_path in user_data.items():
        try:
            dst = os.path.join(main_dist, fname)
            if not os.path.exists(dst):
                shutil.copy2(src_path, dst)
                log(f"  Restored user data: {fname}")
        except Exception as e:
            log(f"  (restore {fname} failed: {e})")

    # 8. 清理 Web 服务独立目录
    if os.path.isdir(web_dist):
        shutil.rmtree(web_dist, ignore_errors=True)


def cleanup_after():
    log("Cleaning temporary files...")
    tmp_dist = os.path.join(PROJECT_ROOT, "_build_tmp")
    shutil.rmtree(tmp_dist, ignore_errors=True)
    for spec in [f"{MAIN_EXE_NAME}.spec", f"{WEB_EXE_NAME}.spec", f"{UPDATE_EXE_NAME}.spec"]:
        spec_path = os.path.join(PROJECT_ROOT, spec)
        if os.path.exists(spec_path):
            os.remove(spec_path)
    build_dir = os.path.join(PROJECT_ROOT, "build")
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir, ignore_errors=True)


def main():
    print("=" * 56)
    print(f"  {APP_NAME} - Build Script")
    print(f"  Version: {VERSION}")
    print(f"  Targets: {MAIN_EXE_NAME}.exe + {WEB_EXE_NAME}.exe")
    print("=" * 56)
    print()

    clean()
    build_main_app()
    build_web_service()
    build_update_exe()
    merge_outputs()
    cleanup_after()

    print()
    print("=" * 56)
    print("  [OK] Build successful!")
    print("=" * 56)
    print()
    print("  Output directory: " + OUTPUT_DIR)
    print("  Main EXE:         " + os.path.join(OUTPUT_DIR, f"{MAIN_EXE_NAME}.exe"))
    print("  Web Service EXE:  " + os.path.join(OUTPUT_DIR, f"{WEB_EXE_NAME}.exe"))
    print("  Update EXE:     " + os.path.join(OUTPUT_DIR, f"{UPDATE_EXE_NAME}.exe"))
    print()
    print("  Update instructions:")
    print(f"  Copy dist\\{OUTPUT_DIR_NAME} to deployment location, overwriting old files.")
    print("  Keep these user data files (in .exe directory):")
    print("    - local_cache.db")
    print("    - .language.json")
    print("    - config.ini")
    print("    - .mms_creds.json")
    print("    - config_backups/")
    print()


if __name__ == "__main__":
    main()



