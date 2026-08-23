"""MMS-Update.exe - Standalone update tool.
Runs independently from MMS-Main.exe to replace locked files.
"""
import os
import sys
import time
import subprocess

# Ensure client/ is on path
_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

from utils.updater import _extract_zip, _get_project_root


def main():
    project_root = _get_project_root()
    update_dir = os.path.join(project_root, "update")
    zip_path = None

    # Find the downloaded update.zip
    # Priority 1: command-line argument
    if len(sys.argv) >= 2:
        zip_path = sys.argv[1]

    # Priority 2: project root left by main.py
    if not zip_path or not os.path.isfile(zip_path):
        zip_path = os.path.join(project_root, "update.zip")

    # Priority 3: tempdir left by main.py
    if not zip_path or not os.path.isfile(zip_path):
        # Check common temp locations
        import tempfile
        tmp = tempfile.gettempdir()
        for f in os.listdir(tmp):
            if f == "mms_update.zip":
                zip_path = os.path.join(tmp, f)
                break

    if not zip_path or not os.path.isfile(zip_path):
        print("No update.zip found, aborting.")
        sys.exit(1)

    print()
    print("=" * 50)
    print("  MMS - Updating...")
    print("=" * 50)
    print()

    # Wait for MMS-Main.exe to fully exit before replacing files
    print("  [WAITING] 等待 MMS-Main.exe 进程退出...")
    waited = 0
    while waited < 15:  # max 15 seconds
        found = False
        try:
            import psutil
            for proc in psutil.process_iter(["name"]):
                if proc.info["name"] == "MMS-Main.exe":
                    found = True
                    break
        except ImportError:
            # Fallback: use tasklist
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq MMS-Main.exe", "/NH"],
                    capture_output=True, text=True, timeout=3
                )
                if "MMS-Main.exe" in result.stdout:
                    found = True
            except Exception:
                found = False
        except Exception:
            found = False

        if not found:
            print("  [OK] MMS-Main.exe 已退出")
            break
        time.sleep(1)
        waited += 1
        print("  [WAITING] ...%d" % waited)

    if waited >= 15:
        print("  [WARN] MMS-Main.exe did not exit in time, proceeding anyway")

    ok = _extract_zip(zip_path, project_root)

    if ok:
        print()
        print("  [OK] Update complete. Starting MMS...")
        print()
        time.sleep(2)

        # Start MMS-Main.exe
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        main_exe = os.path.join(exe_dir, "MMS-Main.exe")
        if os.path.exists(main_exe):
            subprocess.Popen(main_exe, cwd=exe_dir)

        # If web service was running, restart it
        web_exe = os.path.join(exe_dir, "MMS-WebServices.exe")
        if os.path.exists(web_exe):
            # Check if it was running before
            auto_cfg = os.path.join(exe_dir, ".web_autostart.json")
            if os.path.exists(auto_cfg):
                import json
                try:
                    with open(auto_cfg, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    if cfg.get("enabled"):
                        subprocess.Popen(web_exe, cwd=exe_dir)
                except Exception:
                    pass

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
