"""打包并上传更新到 FTP（PLAIN + PASV）"""
import ftplib
import io
import os
import socket
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, r"C:\Users\Administrator\Desktop\mms\client")

from utils.ftp_config import load_update_config
from utils.updater import get_local_version, format_version

FTP_CFG = load_update_config()
PROJECT_ROOT = r"C:\Users\Administrator\Desktop\mms"
DIST_DIR = os.path.join(PROJECT_ROOT, "dist", "物料管理系统-MMS")
TEMP_ZIP = os.path.join(PROJECT_ROOT, "_mms_update_temp.zip")

EXCLUDE_NAMES = {"__pycache__", ".env", "version.txt"}
EXCLUDE_EXT = {".pyc", ".pyd", ".dll"}


def build_zip():
    print(f"打包 {DIST_DIR} -> {TEMP_ZIP}")
    exclude_dirs = {"__pycache__"}
    exclude_exts = {".pyc", ".pyd", ".dll"}
    with zipfile.ZipFile(TEMP_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(DIST_DIR):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for f in files:
                if f in EXCLUDE_NAMES:
                    continue
                if any(f.lower().endswith(ext) for ext in exclude_exts):
                    continue
                full = os.path.join(root, f)
                rel = os.path.relpath(full, DIST_DIR)
                zf.write(full, rel)
    size = os.path.getsize(TEMP_ZIP)
    print(f"  打包完成: {size / 1024 / 1024:.1f} MB")


def upload():
    host = _resolve_ip(FTP_CFG["host"], FTP_CFG["port"])
    port = FTP_CFG["port"]
    user = FTP_CFG["user"]
    passwd = FTP_CFG["pass"]
    directory = FTP_CFG["directory"]

    print(f"FTP: {host}:{port} user={user} dir={directory}")

    ftp = ftplib.FTP()
    ftp.connect(host, port, timeout=30)
    print("  TCP OK")
    ftp.login(user, passwd)
    print("  LOGIN OK")
    ftp.set_pasv(True)
    ftp.cwd(directory)
    print(f"  CWD {directory} OK")

    # 上传 version.txt
    ver = get_local_version()
    ver_bytes = str(ver).encode("utf-8")
    ver_path = os.path.join(os.path.dirname(TEMP_ZIP), "_mms_ver_tmp.txt")
    with open(ver_path, "wb") as f:
        f.write(ver_bytes)
    ftp.voidcmd("TYPE I")
    with open(ver_path, "rb") as f:
        ftp.storbinary("STOR version.txt", f)
    os.unlink(ver_path)
    print(f"  version.txt 上传完成 ({ver} = {format_version(ver)})")

    # 上传 update.zip
    ftp.voidcmd("TYPE I")
    with open(TEMP_ZIP, "rb") as f:
        ftp.storbinary("STOR update.zip", f)
    print(f"  update.zip 上传完成 ({os.path.getsize(TEMP_ZIP) / 1024 / 1024:.1f} MB)")

    ftp.close()
    print("DONE")


def _resolve_ip(host, port):
    try:
        infos = socket.getaddrinfo(host, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
        if infos:
            return infos[0][4][0]
    except Exception:
        pass
    return host


def main():
    print("=" * 60)
    print("上传更新包到 FTP")
    print(f"  版本: {format_version(get_local_version())}")
    print("=" * 60)
    build_zip()
    upload()
    os.unlink(TEMP_ZIP)
    print("临时文件已清理")


if __name__ == "__main__":
    main()