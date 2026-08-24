"""
同步状态栏组件
显示网络连接状态、同步状态、待同步队列数量、手动更新
"""
import os
import shutil
import tempfile
import time

import ftplib

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QProgressDialog, QMenu,
)
from PySide6.QtCore import Signal, QThread, QTimer, Qt
from PySide6.QtGui import QFont, QCursor

from i18n import tr
from utils.theme import COLORS

_MODE_COLOR_MAP = {
    "online": "#059669",
    "semi_offline": COLORS["warning"],
    "offline": COLORS["danger"],
}


class _VersionCheckThread(QThread):
    """Lightweight version check — only compares version numbers, no download."""
    signal_finished = Signal(dict)

    def __init__(self, config):
        super().__init__()
        self.config = config

    def run(self):
        import datetime
        import traceback
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_vchk.log")
        log_path = os.path.normpath(log_path)

        def _dbg(msg):
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"{datetime.datetime.now()} {msg}\n")
            except Exception:
                pass

        try:
            _dbg("THREAD_START")
            _dbg(f"frozen={getattr(sys, 'frozen', False)}")
            _dbg(f"config keys={list(self.config.keys())}")
            _dbg(f"config host={self.config.get('host')}")

            from utils.updater import get_local_version, _connect_ftp, _close_ftp, _get_project_root
            local_ver = get_local_version()
            _dbg(f"local_ver={local_ver}")

            ftp, ver_data, status = _connect_ftp(self.config)
            _dbg(f"connect ftp={'ok' if ftp else 'None'} ver_data_len={len(ver_data) if ver_data else 0}")

            if ftp is None:
                _dbg("connect_fail")
                self.signal_finished.emit({"status": "connect_fail"})
                return

            try:
                remote_ver = int(ver_data.decode("utf-8").strip())
            except Exception as e:
                _dbg(f"invalid_version: {e}")
                _close_ftp(ftp)
                self.signal_finished.emit({"status": "invalid_version"})
                return

            _close_ftp(ftp)
            _dbg(f"remote={remote_ver} local={local_ver}")

            if remote_ver > local_ver:
                _dbg("EMIT new_version")
                self.signal_finished.emit({
                    "status": "new_version",
                    "remote_ver": remote_ver,
                    "local_ver": local_ver,
                })
            else:
                _dbg("EMIT latest")
                self.signal_finished.emit({"status": "latest"})
        except Exception as e:
            _dbg(f"EXCEPTION: {type(e).__name__}: {e}")
            _dbg(traceback.format_exc())
            self.signal_finished.emit({"status": "latest"})


class _ManualUpdateThread(QThread):
    signal_finished = Signal(dict)
    signal_progress = Signal(str, int)

    def __init__(self, config):
        super().__init__()
        self.config = config

    def run(self):
        try:
            from utils.updater import (
                get_local_version, _connect_ftp, _close_ftp,
                _verify_zip, _get_project_root,
            )
            local_ver = get_local_version()
            tmpdir = tempfile.mkdtemp()
            zip_path = os.path.join(tmpdir, "update.zip")

            self.signal_progress.emit(tr("toast.update_checking"), 10)

            ftp, ver_data, status = _connect_ftp(self.config)
            if status == "NO_FILES":
                _cleanup_update_tmp(tmpdir, zip_path)
                self.signal_finished.emit({"status": "no_files"})
                return
            if ftp is None:
                _cleanup_update_tmp(tmpdir, zip_path)
                self.signal_finished.emit({"status": "connect_fail"})
                return

            try:
                remote_ver = int(ver_data.decode("utf-8").strip())
            except Exception:
                _close_ftp(ftp)
                _cleanup_update_tmp(tmpdir, zip_path)
                self.signal_finished.emit({"status": "invalid_version"})
                return

            if remote_ver <= local_ver:
                _close_ftp(ftp)
                _cleanup_update_tmp(tmpdir, zip_path)
                self.signal_finished.emit({"status": "same_version", "local_ver": local_ver})
                return

            self.signal_progress.emit(tr("toast.update_downloading"), 30)

            # 检查 update.zip 是否存在于 FTP 服务器
            ftp_files = []
            try:
                ftp_files = ftp.nlst()
            except Exception:
                pass
            try:
                ftp_pwd = ftp.pwd()
            except Exception:
                ftp_pwd = ""

            try:
                ftp.voidcmd("TYPE I")
                try:
                    size = int(ftp.size("update.zip"))
                except ftplib.error_perm:
                    _close_ftp(ftp)
                    _cleanup_update_tmp(tmpdir, zip_path)
                    file_list = ", ".join(ftp_files) if ftp_files else "（无）"
                    self.signal_finished.emit({
                        "status": "download_fail",
                        "error": (
                            "update.zip 不存在于 FTP 目录 %s\n"
                            "FTP 当前文件：%s\n"
                            "请将打包好的 MMS-Main 目录压缩为 update.zip 后上传到该目录"
                        ) % (ftp_pwd or "/MMSUpdates", file_list),
                    })
                    return
                if size == 0:
                    _close_ftp(ftp)
                    _cleanup_update_tmp(tmpdir, zip_path)
                    self.signal_finished.emit({
                        "status": "download_fail",
                        "error": "update.zip 在 FTP 服务器上为空，请重新上传",
                    })
                    return
            except Exception as e:
                last_error = "无法检查 update.zip: %s" % e
                pass

            downloaded = False
            last_error = ""
            try:
                for _attempt in range(3):
                    for pasv in (True, False):
                        try:
                            ftp.set_pasv(pasv)
                            ftp.voidcmd("TYPE I")
                            with open(zip_path, "wb") as zf_out:
                                ftp.retrbinary("RETR update.zip", zf_out.write)
                            if os.path.getsize(zip_path) > 0:
                                downloaded = True
                                raise _UpdateDone
                        except _UpdateDone:
                            raise
                        except Exception as e:
                            last_error = str(e)
                            import time
                            time.sleep(0.5)
            except _UpdateDone:
                pass
            else:
                _close_ftp(ftp)
                _cleanup_update_tmp(tmpdir, zip_path)
                self.signal_finished.emit({"status": "download_fail", "error": last_error})
                return

            _close_ftp(ftp)

            self.signal_progress.emit(tr("toast.update_verify"), 60)
            if not _verify_zip(zip_path):
                _cleanup_update_tmp(tmpdir, zip_path)
                self.signal_finished.emit({"status": "verify_fail"})
                return

            self.signal_progress.emit(tr("toast.update_ready"), 80)
            project_root = _get_project_root()
            update_zip_dst = os.path.join(project_root, "update.zip")
            try:
                if os.path.exists(update_zip_dst):
                    os.remove(update_zip_dst)
                shutil.copy2(zip_path, update_zip_dst)
                _cleanup_update_tmp(tmpdir, zip_path)
            except Exception as e:
                _cleanup_update_tmp(tmpdir, zip_path)
                self.signal_finished.emit({"status": "extract_fail", "error": str(e)})
                return

            self.signal_progress.emit(tr("toast.update_ready"), 95)
            self.signal_finished.emit({"status": "ready", "remote_ver": remote_ver})
        except Exception as e:
            self.signal_finished.emit({"status": "error", "error": str(e)})


def _cleanup_update_tmp(tmpdir, zip_path):
    try:
        if zip_path and os.path.isfile(zip_path):
            os.unlink(zip_path)
    except Exception:
        pass
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass


class _UpdateDone(Exception):
    pass


class SyncStatusBar(QWidget):
    """同步状态栏组件"""

    force_sync_clicked = Signal()
    language_switch_clicked = Signal()
    manual_update_clicked = Signal()
    update_available_changed = Signal(bool, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_sync_status = None
        self._last_network_online = None
        self._last_queue_count = 0
        self._last_mode = None
        self._last_sync_time_str = "--"
        self._last_syncing = False
        self._update_thread = None
        self._update_prog_dialog = None
        self._update_timer = None
        self._current_workshop = ""
        self._version_check_thread = None
        self._update_available = False
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 4, 16, 4)
        layout.setSpacing(12)

        self.network_label = QLabel(tr("ssb.network_detecting"))
        layout.addWidget(self.network_label)

        self.mode_label = QLabel(tr("ssb.mode_online"))
        self.mode_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.mode_label)

        self.sync_label = QLabel(tr("ssb.sync_waiting"))
        layout.addWidget(self.sync_label)

        self.queue_label = QLabel(tr("ssb.queue", count=0))
        layout.addWidget(self.queue_label)

        layout.addStretch()

        self.lang_btn = QPushButton("🌐 中文 / ES")
        self.lang_btn.setObjectName("secondaryButton")
        self.lang_btn.setMaximumWidth(130)
        self.lang_btn.setToolTip(tr("ssb.lang_tooltip"))
        self.lang_btn.clicked.connect(self._on_lang_clicked)
        layout.addWidget(self.lang_btn)

        self.sync_btn = QPushButton(tr("ssb.force_sync"))
        self.sync_btn.setObjectName("secondaryButton")
        self.sync_btn.setMinimumWidth(80)
        self.sync_btn.clicked.connect(self.force_sync_clicked.emit)
        layout.addWidget(self.sync_btn)

        self.update_btn = QPushButton(tr("ssb.manual_update"))
        self.update_btn.setObjectName("secondaryButton")
        self.update_btn.setMinimumWidth(90)
        self.update_btn.setToolTip(tr("ssb.update_tooltip"))
        self.update_btn.clicked.connect(self._trigger_manual_update)
        layout.addWidget(self.update_btn)

        self.workshop_btn = QPushButton(tr("ssb.workshop_switch"))
        self.workshop_btn.setObjectName("secondaryButton")
        self.workshop_btn.setMinimumWidth(100)
        self.workshop_btn.setToolTip(tr("ssb.workshop_tooltip"))
        self.workshop_btn.clicked.connect(self._on_workshop_btn_clicked)
        layout.addWidget(self.workshop_btn)

        self.last_sync_label = QLabel(tr("ssb.last_sync", time="--"))
        layout.addWidget(self.last_sync_label)

        self._update_workshop_btn_text()

    def _on_lang_clicked(self):
        self.language_switch_clicked.emit()

    def _update_workshop_btn_text(self):
        from utils.app_config import load_workshop_config
        from config import DEFAULT_WORKSHOP
        try:
            cfg = load_workshop_config()
            name = cfg.get("current_workshop", "") or DEFAULT_WORKSHOP
        except Exception:
            name = DEFAULT_WORKSHOP
        self._current_workshop = name
        self.workshop_btn.setText(f"🏭 {name}")

    def _on_workshop_btn_clicked(self):
        from utils.app_config import load_workshop_config
        from config import DEFAULT_WORKSHOP
        from widgets.toast import toast_info

        try:
            cfg = load_workshop_config()
        except Exception:
            cfg = {}
        raw = cfg.get("workshops", "") or ""
        list_items = [w.strip() for w in raw.split(",") if w.strip()]
        if not list_items:
            list_items = [DEFAULT_WORKSHOP]

        if len(list_items) <= 1:
            toast_info(self, tr("ssb.workshop_single"))
            return

        current = self._current_workshop or DEFAULT_WORKSHOP
        menu = QMenu(self)
        for ws in list_items:
            action = menu.addAction(ws)
            if ws == current:
                action.setCheckable(True)
                action.setChecked(True)
            ws_name = ws
            action.triggered.connect(lambda _, n=ws_name: self._switch_workshop(n))
        menu.exec(QCursor.pos())

    def _switch_workshop(self, name: str):
        from utils.app_config import save_workshop_config
        from widgets.toast import toast_info
        from utils.updater import restart_main

        if name == self._current_workshop:
            return
        try:
            save_workshop_config({"current_workshop": name})
        except Exception as e:
            from widgets.toast import toast_error
            toast_error(self, str(e))
            return
        toast_info(self, tr("ssb.workshop_switching").format(name=name))
        QTimer.singleShot(1500, lambda: restart_main())

    def _trigger_manual_update(self):
        from widgets.toast import toast_info, toast_error
        from utils.ftp_config import load_update_config

        cfg = load_update_config()
        host = cfg.get("host", "")
        if not host:
            toast_info(self, tr("toast.update_no_host"))
            return

        config = {
            "host": host,
            "port": cfg.get("port", 21),
            "user": cfg.get("user", ""),
            "pass": cfg.get("pass", ""),
            "directory": cfg.get("directory", ""),
        }

        self._update_prog_dialog = QProgressDialog(tr("toast.update_checking"), "", 0, 100)
        self._update_prog_dialog.setMinimumDuration(0)
        self._update_prog_dialog.setWindowModality(Qt.WindowModal)
        self._update_prog_dialog.setFont(QFont("Microsoft YaHei", 10))
        self._update_prog_dialog.setValue(0)
        self._update_prog_dialog.show()

        self._update_thread = _ManualUpdateThread(config)
        self._update_thread.signal_progress.connect(self._on_manual_update_progress)
        self._update_thread.signal_finished.connect(self._on_manual_update_finished)
        self._update_thread.start()

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(120000)
        self._update_timer.timeout.connect(self._on_manual_update_timeout)
        self._update_timer.start()

        self.update_btn.setEnabled(False)

    def _on_manual_update_progress(self, text, percent):
        if self._update_prog_dialog and self._update_prog_dialog.isVisible():
            self._update_prog_dialog.setLabelText(text)
            self._update_prog_dialog.setValue(percent)

    def _on_manual_update_finished(self, result):
        from widgets.toast import toast_info, toast_success, toast_error
        from utils.updater import format_version, restart_self

        try:
            if self._update_timer:
                self._update_timer.stop()
                self._update_timer.deleteLater()
                self._update_timer = None

            if self._update_prog_dialog:
                self._update_prog_dialog.setValue(100)
                self._update_prog_dialog.close()
                self._update_prog_dialog.deleteLater()
                self._update_prog_dialog = None

            status = result.get("status", "")
            if status == "ready":
                remote_ver = result.get("remote_ver", 0)
                toast_success(self, tr("toast.update_success").format(new_ver=format_version(remote_ver)), 2500)
                QTimer.singleShot(2500, lambda: restart_self())
            elif status == "verify_fail":
                toast_error(self, tr("toast.update_verify_fail"))
            elif status == "extract_fail":
                toast_error(self, tr("toast.update_extract_fail"))
            elif status == "no_files":
                toast_info(self, tr("toast.update_no_files"))
            elif status == "same_version":
                local_ver = result.get("local_ver", 0)
                toast_info(self, tr("toast.update_same_version").format(ver=format_version(local_ver)))
            elif status == "invalid_version":
                toast_error(self, tr("toast.update_invalid_version"))
            elif status == "download_fail":
                err = result.get("error", "")
                toast_error(self, tr("toast.update_download_fail") + (f" ({err})" if err else ""))
            elif status == "connect_fail":
                toast_error(self, tr("toast.update_connect_fail"))
            else:
                err = result.get("error", "")
                toast_error(self, err or tr("toast.update_download_fail"))
        except Exception as e:
            toast_error(self, str(e))
        finally:
            self.update_btn.setEnabled(True)

    def _on_manual_update_timeout(self):
        if self._update_prog_dialog:
            self._update_prog_dialog.close()
            self._update_prog_dialog = None
        if self._update_thread:
            try:
                self._update_thread.quit()
                self._update_thread.wait(3000)
            except Exception:
                pass
        self.update_btn.setEnabled(True)

    def set_update_available(self, available: bool, remote_ver: int = 0):
        self._update_available = available
        self.update_available_changed.emit(available, remote_ver)

    def check_version_on_startup(self):
        from utils.ftp_config import load_update_config
        try:
            cfg = load_update_config()
        except Exception:
            return
        if not cfg.get("host", ""):
            return
        config = {
            "host": cfg.get("host", ""),
            "port": cfg.get("port", 21),
            "user": cfg.get("user", ""),
            "pass": cfg.get("pass", ""),
            "directory": cfg.get("directory", ""),
        }
        self._version_check_thread = _VersionCheckThread(config)
        self._version_check_thread.signal_finished.connect(self._on_version_check_finished)
        self._version_check_thread.start()

    def _on_version_check_finished(self, result):
        status = result.get("status", "")
        if status == "new_version":
            self.set_update_available(True, result.get("remote_ver", 0))
        else:
            self.set_update_available(False, 0)

    def set_network_status(self, is_online: bool):
        self._last_network_online = is_online
        if is_online:
            self.network_label.setText(tr("ssb.network_online"))
            self.network_label.setObjectName("syncStatusOnline")
        else:
            self.network_label.setText(tr("ssb.network_offline"))
            self.network_label.setObjectName("syncStatusOffline")
        self.network_label.style().unpolish(self.network_label)
        self.network_label.style().polish(self.network_label)

    def set_sync_status(self, status: str):
        self._last_sync_status = status
        status_map = {
            "online": (tr("ssb.sync_synced"), "syncStatusOnline"),
            "offline": (tr("ssb.sync_offline"), "syncStatusOffline"),
            "syncing": (tr("ssb.sync_syncing"), "syncStatusSyncing"),
        }
        text, obj_name = status_map.get(status, (tr("ssb.sync_unknown"), ""))
        self.sync_label.setText(text)
        if obj_name:
            self.sync_label.setObjectName(obj_name)
            self.sync_label.style().unpolish(self.sync_label)
            self.sync_label.style().polish(self.sync_label)

    def set_queue_count(self, count: int):
        self._last_queue_count = count
        self.queue_label.setText(tr("ssb.queue", count=count))
        if count > 0:
            self.queue_label.setStyleSheet(f"color: {COLORS['warning']}; font-weight: bold;")
        else:
            self.queue_label.setStyleSheet("color: #5a6573;")

    def set_mode(self, mode: str):
        self._last_mode = mode
        color = _MODE_COLOR_MAP.get(mode, "#5a6573")
        text_map = {
            "online": tr("ssb.mode_online"),
            "semi_offline": tr("ssb.mode_semi_offline"),
            "offline": tr("ssb.mode_offline"),
        }
        text = text_map.get(mode, f"模式: {mode}")
        self.mode_label.setText(text)
        self.mode_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def set_last_sync_time(self, time_str: str):
        self._last_sync_time_str = time_str
        self.last_sync_label.setText(tr("ssb.last_sync", time=time_str))

    def set_syncing(self, is_syncing: bool):
        self._last_syncing = is_syncing
        self.sync_btn.setEnabled(not is_syncing)
        if is_syncing:
            self.sync_btn.setText(tr("ssb.syncing_now"))
        else:
            self.sync_btn.setText(tr("ssb.force_sync"))

    def retranslate_ui(self):
        self.network_label.setText(tr("ssb.network_detecting"))
        self.mode_label.setText(tr("ssb.mode_online"))
        self.sync_label.setText(tr("ssb.sync_waiting"))
        self.queue_label.setText(tr("ssb.queue", count=self._last_queue_count))
        self.last_sync_label.setText(tr("ssb.last_sync", time=self._last_sync_time_str))
        self.sync_btn.setText(tr("ssb.syncing_now") if self._last_syncing else tr("ssb.force_sync"))
        self.update_btn.setText(tr("ssb.manual_update"))
        self.workshop_btn.setText(tr("ssb.workshop_switch"))
        self.workshop_btn.setToolTip(tr("ssb.workshop_tooltip"))
        self.lang_btn.setToolTip(tr("ssb.lang_tooltip"))
        if self._last_network_online is not None:
            self.set_network_status(self._last_network_online)
        if self._last_sync_status:
            self.set_sync_status(self._last_sync_status)
        if self._last_mode:
            self.set_mode(self._last_mode)
        self.set_queue_count(self._last_queue_count)
        self._update_workshop_btn_text()

    def update_lang_button(self, lang: str):
        if lang == "zh_CN":
            self.lang_btn.setText("🌐 中文 / ES")
        else:
            self.lang_btn.setText("🌐 ES / 中文")