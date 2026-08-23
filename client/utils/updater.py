"""MMS Updater / FTP auto-update module"""
import io
import ftplib
import logging
import os
import posixpath
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile

_LOG = logging.getLogger(__name__)

class _Done(Exception):
    pass

def _get_project_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _get_version_file() -> str:
    return os.path.join(_get_project_root(), "version.txt")

def get_local_version() -> int:
    try:
        with open(_get_version_file(), "r", encoding="utf-8-sig") as f:
            return int(f.read().strip())
    except Exception:
        return 0

def format_version(v: int) -> str:
    if v <= 0:
        return "No update"
    return str(v)

def set_local_version(v: int):
    """Write version.txt atomically with fsync + os.replace"""
    try:
        target = _get_version_file()
        d = tempfile.gettempdir()
        tmp = os.path.join(d, "_mms_version_{}.tmp".format(os.getpid()))
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(str(v))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except Exception:
        pass

def _close_ftp(ftp):
    try:
        ftp.close()
    except Exception:
        pass

def _resolve_ip(host: str, port: int) -> str:
    """Resolve IPv4 to avoid ftplib IPv6 issues"""
    try:
        infos = socket.getaddrinfo(host, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
        if infos:
            return infos[0][4][0]
    except Exception:
        pass
    return host

def _connect_ftp(config: dict):
    """Connect to FTP server and check version.
    Returns (ftp, version_bytes, status):
        status "OK"       = connected and downloaded version.txt
        status "NO_FILES" = connected but no version.txt (server needs upload)
        status None       = could not connect at all
    """
    host = config["host"]
    port = config.get("port", 21)
    host = _resolve_ip(host, port)
    user = config["user"]
    passwd = config["pass"]
    directory = config.get("directory", "/")
    modes = [
        ("plain", True),
        ("plain", False),
        ("tls",  True),
        ("tls",  False),
    ]
    MAX_ROUNDS = 3
    DATA_RETRY = 2
    TLS_CONNECT_TIMEOUT = 3
    PLAIN_CONNECT_TIMEOUT = 10

    def _close_ftp_inner(ftp):
        try:
            ftp.close()
        except Exception:
            pass

    def try_connect(proto, use_pasv):
        timeout = TLS_CONNECT_TIMEOUT if proto == "tls" else PLAIN_CONNECT_TIMEOUT
        ftp = ftplib.FTP_TLS() if proto == "tls" else ftplib.FTP()
        try:
            _LOG.debug("FTP trying: %s + %s (timeout=%s)", proto.upper(),
                        "PASV" if use_pasv else "PORT", timeout)
            ftp.connect(host, port, timeout=timeout)
            if proto == "tls":
                ftp.auth()
                ftp.login(user, passwd)
                try:
                    ftp.prot_p()
                except Exception:
                    _close_ftp_inner(ftp)
                    raise
            else:
                ftp.login(user, passwd)
            ftp.set_pasv(use_pasv)
            _ensure_remote_dir(ftp, directory)
            ftp.cwd(directory)
            ftp.voidcmd("TYPE I")
        except Exception:
            _close_ftp_inner(ftp)
            raise
        return ftp

    def download_version(ftp):
        for attempt in range(DATA_RETRY + 1):
            try:
                buf = io.BytesIO()
                ftp.retrbinary("RETR version.txt", buf.write)
                return buf.getvalue()
            except ftplib.error_perm:
                return None
        return None

    connected_ever = False
    got_no_files = False
    for round_ in range(MAX_ROUNDS):
        for proto, use_pasv in modes:
            ftp = None
            try:
                ftp = try_connect(proto, use_pasv)
                connected_ever = True
                ver_data = download_version(ftp)
                if ver_data is not None:
                    result = (ftp, ver_data, "OK")
                    ftp = None
                    return result
                got_no_files = True
                _close_ftp_inner(ftp)
                ftp = None
            except Exception:
                pass
            finally:
                if ftp is not None:
                    _close_ftp_inner(ftp)
                    ftp = None
        if round_ < MAX_ROUNDS - 1:
            time.sleep(0.5)
    if got_no_files:
        return (None, None, "NO_FILES")
    return (None, None, None)

def _ensure_remote_dir(ftp: ftplib.FTP, directory: str):
    parts = [p for p in directory.split("/") if p]
    current = "/"
    for part in parts:
        try:
            current = os.path.join(current, part).replace("\\", "/")
            ftp.cwd(current)
        except ftplib.error_perm:
            ftp.mkd(current)
            ftp.cwd(current)

def _safe_extract_path(project_root: str, filename: str):
    filename_norm = posixpath.normpath(filename)
    if filename_norm.startswith("..") or filename_norm.startswith("/"):
        return None
    target = os.path.normpath(os.path.join(project_root, filename_norm))
    root_norm = os.path.normpath(project_root).rstrip(os.sep)
    if target == root_norm:
        return None
    if not target.startswith(root_norm + os.sep):
        return None
    return target

def _verify_zip(zip_path: str) -> bool:
    """Verify ZIP integrity (structure + signature + full CRC check)."""
    try:
        if not zipfile.is_zipfile(zip_path):
            return False
        size = os.path.getsize(zip_path)
        if size < 22:
            return False
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            if not names:
                return False
            for name in names:
                info = zf.getinfo(name)
                if info.is_dir() or info.file_size == 0:
                    continue
                data = zf.read(name)
                if len(data) != info.file_size:
                    return False
                import zlib
                crc = zlib.crc32(data) & 0xFFFFFFFF
                if crc != (info.CRC & 0xFFFFFFFF):
                    return False
            bad = zf.testzip()
            return bad is None
    except Exception:
        return False


_console_log_proc = None

def _console_log(msg: str):
    """Write a message to the visible console window during update.
    Uses a persistent cmd.exe process so the window stays open and messages scroll."""
    global _console_log_proc
    if _console_log_proc is not None:
        # Write to the existing cmd process stdin
        try:
            _console_log_proc.stdin.write("echo " + msg + "\n")
            _console_log_proc.stdin.flush()
        except Exception:
            _console_log_proc = None
    if _console_log_proc is None:
        # Start a new cmd window
        try:
            _console_log_proc = subprocess.Popen(
                ["cmd", "/c", "title MMS Update && echo."],
                stdin=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                cwd=os.getcwd(),
            )
        except Exception:
            _console_log_proc = None

def _extract_zip(zip_path: str, project_root: str) -> bool:
    """Extract update.zip and replace all files.
    MMS-Update.exe is a single-file exe (--onefile), so it does not depend on
    _internal/ and can safely replace it.
    Supports both flat zip (_internal/ + MMS-Main.exe at root) and nested zip
    (single top-level dir containing the files).
    """
    try:
        update_dir = os.path.join(project_root, "update")
        internal_root = os.path.join(project_root, "_internal")
        main_exe = os.path.join(project_root, "MMS-Main.exe")
        web_exe = os.path.join(project_root, "MMS-WebServices.exe")

        if os.path.isdir(update_dir):
            try:
                shutil.rmtree(update_dir, ignore_errors=True)
            except Exception:
                pass
        os.makedirs(update_dir, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

        # Detect if zip has a single top-level directory
        top_dirs = {}
        for name in names:
            parts = name.split("/")
            if len(parts) >= 2:
                top_dirs.setdefault(parts[0], []).append(name)
        if len(top_dirs) == 1:
            top_name, nested_names = next(iter(top_dirs.items()))
            prefix = top_name + "/"
            names = [n[len(prefix):] if n.startswith(prefix) else n for n in nested_names]

        extracted = False
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                target = _safe_extract_path(update_dir, info.filename)
                if target is None:
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(info) as src_f, open(target, "wb") as dst_f:
                    shutil.copyfileobj(src_f, dst_f)
                extracted = True
        if not extracted:
            print("  [ERROR] zip 为空或无法提取")
            return False
        print("  [OK] Extracted update.zip")

        # Replace _internal/
        src_internal = os.path.join(update_dir, "_internal")
        if os.path.isdir(src_internal):
            if os.path.isdir(internal_root):
                for attempt in range(5):
                    try:
                        shutil.rmtree(internal_root, ignore_errors=True)
                        break
                    except (PermissionError, OSError):
                        time.sleep(2)
                if os.path.isdir(internal_root):
                    print("  [!] Old _internal/ still exists, merging...")
            shutil.copytree(src_internal, internal_root, dirs_exist_ok=True)
            print("  [OK] Replaced _internal/")
        else:
            print("  [!] _internal/ not found in zip")

        # Replace MMS-Main.exe
        src_main = os.path.join(update_dir, "MMS-Main.exe")
        if os.path.isfile(src_main):
            try:
                if os.path.exists(main_exe):
                    os.remove(main_exe)
                shutil.copy2(src_main, main_exe)
                print("  [OK] Replaced MMS-Main.exe")
            except Exception as e:
                print("  [!] MMS-Main.exe: %s" % e)
        else:
            print("  [!] MMS-Main.exe not found in zip")

        # Replace MMS-WebServices.exe
        src_web = os.path.join(update_dir, "MMS-WebServices.exe")
        if os.path.isfile(src_web):
            try:
                if os.path.exists(web_exe):
                    os.remove(web_exe)
                shutil.copy2(src_web, web_exe)
                print("  [OK] Replaced MMS-WebServices.exe")
            except Exception as e:
                print("  [!] MMS-WebServices.exe: %s" % e)

        # Start MMS-Main.exe
        time.sleep(1)
        if os.path.isfile(main_exe):
            print("  [STARTING] Starting MMS-Main.exe...")
            subprocess.Popen(main_exe, cwd=project_root)
        else:
            print("  [ERROR] MMS-Main.exe not found after update")

        # Update version.txt
        version_file = os.path.join(project_root, "version.txt")
        try:
            ver_src = os.path.join(update_dir, "_internal", "version.txt")
            if not os.path.isfile(ver_src):
                ver_src = os.path.join(update_dir, "version.txt")
            if os.path.isfile(ver_src):
                with open(ver_src, "r", encoding="utf-8") as f:
                    ver = f.read().strip() or "0"
                with open(version_file, "w", encoding="utf-8") as f:
                    f.write(ver)
                print("  [OK] Updated version.txt -> %s" % ver)
        except Exception as e:
            print("  [!] version.txt: %s" % e)

        try:
            shutil.rmtree(update_dir, ignore_errors=True)
        except Exception:
            pass
        print("  [OK] Update complete")
        return True
    except Exception as e:
        print("  [ERROR] Update failed: %s" % e)
        import traceback
        traceback.print_exc()
        return False


def pull_check(config: dict) -> bool:
    try:
        local_version = get_local_version()
        ftp, ver_data, status = _connect_ftp(config)
        if ftp is None:
            _LOG.info("pull_check: connect failed status=%s", status)
            return {"ok": False}
        try:
            remote_version = int(ver_data.decode("utf-8").strip()) if ver_data else 0
        except Exception:
            _close_ftp(ftp)
            return {"ok": False}
        if remote_version <= local_version:
            _close_ftp(ftp)
            return {"ok": False}
        tmpdir = tempfile.mkdtemp()
        zip_path = os.path.join(tmpdir, "update.zip")
        downloaded = False
        last_err = ""
        try:
            for attempt in range(3):
                for pasv in (True, False):
                    try:
                        _LOG.debug("pull_check: download update.zip pasv=%s attempt=%s",
                                   pasv, attempt)
                        ftp.set_pasv(pasv)
                        ftp.voidcmd("TYPE I")
                        with open(zip_path, "wb") as zf_out:
                            ftp.retrbinary("RETR update.zip", zf_out.write)
                        if os.path.getsize(zip_path) > 0:
                            _LOG.info("pull_check: downloaded %d bytes",
                                      os.path.getsize(zip_path))
                            downloaded = True
                            raise _Done
                    except _Done:
                        raise
                    except Exception as e:
                        last_err = str(e)
                        _LOG.warning("pull_check: download failed pasv=%s err=%s", pasv, e)
                        time.sleep(0.3)
        except _Done:
            pass
        finally:
            _close_ftp(ftp)
        if not downloaded:
            shutil.rmtree(tmpdir, ignore_errors=True)
            return {"ok": False}
        if not _verify_zip(zip_path):
            shutil.rmtree(tmpdir, ignore_errors=True)
            return {"ok": False}
        return {
            "ok": True,
            "zip_path": zip_path,
            "tmpdir": tmpdir,
            "remote_version": remote_version,
            "local_version": local_version,
        }
    except Exception:
        return {"ok": False}

def push_update(config: dict):
    try:
        new_version = get_local_version() + 1
        project_root = _get_project_root()
        tmpdir = tempfile.mkdtemp()
        zip_path = os.path.join(tmpdir, "update.zip")

        # 排除：用户数据文件、构建产物、缓存目录
        EXCLUDE_FILES = {
            "update.zip", "version.txt",
            ".language.json", "config.ini",
            ".mms_creds.json", ".login_completed.json",
            ".remember_login.json", ".auto_export.json",
            "_mms_restart.bat",
        }
        EXCLUDE_DIRS = {
            "__pycache__", "build", "dist", "_build_tmp",
            "update", "config_backups", ".git", ".vscode",
            "tests", "MySQL_", "logs", "log",
        }
        EXCLUDE_EXTS = {".db", ".db-wal", ".db-shm", ".py", ".spec", ".bat"}

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, dirnames, filenames in os.walk(project_root):
                dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
                for fn in filenames:
                    if fn in EXCLUDE_FILES:
                        continue
                    if fn.lower().endswith(tuple(ext.upper() for ext in EXCLUDE_EXTS)):
                        continue
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, project_root)
                    zf.write(full, rel)
        ftp, _, _ = _connect_ftp(config)
        if ftp is None:
            shutil.rmtree(tmpdir, ignore_errors=True)
            return (False, "FTP connect failed")
        try:
            for pasv in (True, False):
                for _ in range(2):
                    try:
                        ftp.set_pasv(pasv)
                        ftp.voidcmd("TYPE I")
                        with open(zip_path, "rb") as f:
                            ftp.storbinary("STOR update.zip", f.read)
                        version_bytes = str(new_version).encode("utf-8")
                        ftp.storbinary("STOR version.txt", io.BytesIO(version_bytes).read)
                        raise _Done
                    except _Done:
                        raise
                    except Exception:
                        time.sleep(0.3)
        except _Done:
            pass
        else:
            _close_ftp(ftp)
            shutil.rmtree(tmpdir, ignore_errors=True)
            return (False, "upload failed")
        finally:
            _close_ftp(ftp)
        set_local_version(new_version)
        shutil.rmtree(tmpdir, ignore_errors=True)
        return (True, new_version)
    except Exception as e:
        return (False, str(e))

def restart_self():
    """关闭资源并启动 MMS-Update.exe 执行更新（更新流程专用）"""
    _stop_resources()
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        update_exe = os.path.join(exe_dir, "MMS-Update.exe")
        update_zip = os.path.join(exe_dir, "update.zip")
        bat_path = os.path.join(exe_dir, "_mms_restart.bat")
        with open(bat_path, "w", encoding="gbk") as f:
            f.write("@echo off\n")
            f.write("title MMS Update\n")
            f.write("echo.\n")
            f.write("echo [WAITING] 等待旧进程退出...\n")
            f.write("ping 127.0.0.1 -n 4 >nul\n")
            f.write('echo [STARTING] 正在执行更新...\n')
            f.write('start "" "%s" "%s"\n' % (update_exe, update_zip))
            f.write("echo [OK]\n")
            f.write("ping 127.0.0.1 -n 2 >nul\n")
            f.write("del " + chr(34) + "%%~f0" + chr(34) + "\n")
        subprocess.Popen(
            ["cmd", "/c", bat_path],
            cwd=exe_dir,
            creationflags=subprocess.DETACHED_PROCESS,
        )
    else:
        _update_py = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "MMS-Update.py",
        )
        _update_zip = os.path.join(_get_project_root(), "update.zip")
        subprocess.Popen([sys.executable, _update_py, _update_zip])
        os._exit(0)


def _stop_resources():
    """关闭后台资源（同步引擎、网络监控、MySQL 连接）"""
    try:
        from sync_engine import sync_engine
        sync_engine.stop()
    except Exception:
        pass
    try:
        from network_monitor import network_monitor
        network_monitor.stop()
    except Exception:
        pass
    try:
        from mysql_client import MySQLClient
        mc = MySQLClient()
        mc.close()
    except Exception:
        pass


def restart_main():
    """关闭资源并重启 MMS-Main.exe（车间切换等场景使用）"""
    _stop_resources()
    if getattr(sys, "frozen", False):
        main_exe = sys.executable
        bat_path = os.path.join(os.path.dirname(os.path.abspath(main_exe)), "_mms_restart.bat")
        with open(bat_path, "w", encoding="gbk") as f:
            f.write("@echo off\n")
            f.write("title MMS Restart\n")
            f.write("echo.\n")
            f.write("echo [WAITING] 等待旧进程退出...\n")
            f.write("ping 127.0.0.1 -n 4 >nul\n")
            f.write('echo [STARTING] 正在重启 MMS...\n')
            f.write('start "" "%s"\n' % main_exe)
            f.write("echo [OK]\n")
            f.write("ping 127.0.0.1 -n 2 >nul\n")
            f.write("del " + chr(34) + "%%~f0" + chr(34) + "\n")
        subprocess.Popen(
            ["cmd", "/c", bat_path],
            cwd=os.path.dirname(os.path.abspath(main_exe)),
            creationflags=subprocess.DETACHED_PROCESS,
        )
    else:
        subprocess.Popen([sys.executable] + sys.argv, cwd=os.getcwd())
    os._exit(0)
