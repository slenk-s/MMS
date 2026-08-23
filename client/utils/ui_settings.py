"""
UI 状态持久化模块
将窗口几何、列宽等 UI 偏好保存到 config_backups 目录下最新的 JSON 备份文件中。
每次登录时 _auto_backup_config_on_login 会将当前 UI 状态一并写入备份；
运行期间保存列宽时也会实时更新最新的备份文件。
"""
import json
import os
import glob


_BACKUP_DIR = None


def _get_backup_dir():
    global _BACKUP_DIR
    if _BACKUP_DIR is None:
        from config import LOCAL_DB_PATH
        _BACKUP_DIR = os.path.join(os.path.dirname(LOCAL_DB_PATH), "config_backups")
        os.makedirs(_BACKUP_DIR, exist_ok=True)
    return _BACKUP_DIR


def _latest_backup_path():
    pattern = os.path.join(_get_backup_dir(), "config_*.json")
    files = sorted(glob.glob(pattern), reverse=True)
    return files[0] if files else None


def _load_latest() -> dict:
    path = _latest_backup_path()
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_to_latest(data: dict):
    path = _latest_backup_path()
    if not path:
        # 没有备份文件时，自动创建一个新的
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(_get_backup_dir(), f"config_{ts}.json")
        data.setdefault("backup_time", datetime.now().isoformat())
        data.setdefault("username", "")
        data.setdefault("app_version", "")
        data.setdefault("configs", [])
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def save_window_geometry(geometry, state=None):
    """保存窗口几何和状态到最新备份文件"""
    data = _load_latest()
    ui = data.setdefault("ui_settings", {})
    geo_raw = bytes(geometry.data()) if hasattr(geometry, "data") else geometry
    ui["window_geometry"] = bytes(geo_raw).hex()
    if state is not None:
        st_raw = bytes(state.data()) if hasattr(state, "data") else state
        ui["window_state"] = bytes(st_raw).hex()
    _save_to_latest(data)


def restore_window_geometry() -> tuple:
    """从最新备份文件恢复窗口几何和状态"""
    data = _load_latest()
    ui = data.get("ui_settings", {})
    geo_hex = ui.get("window_geometry", "")
    state_hex = ui.get("window_state", "")
    geometry = bytes.fromhex(geo_hex) if geo_hex else None
    state = bytes.fromhex(state_hex) if state_hex else None
    return geometry, state


def save_column_widths(table_id: str, widths: list):
    """保存某个表格的列宽到最新备份文件"""
    data = _load_latest()
    ui = data.setdefault("ui_settings", {})
    ui.setdefault("column_widths", {})[table_id] = widths
    _save_to_latest(data)


def restore_column_widths(table_id: str) -> list:
    """从最新备份文件恢复某个表格的列宽"""
    data = _load_latest()
    widths = data.get("ui_settings", {}).get("column_widths", {}).get(table_id)
    return widths if isinstance(widths, list) else []


def update_backup_with_ui(data: dict):
    """在 _auto_backup_config_on_login 中调用，将当前内存中的 UI 状态写入备份。
    data 是即将写入备份的 dict（含 backup_time/username/app_version/configs）。
    读取内存中现有的 ui_settings 并合并进去。
    """
    existing = _load_latest()
    ui = existing.get("ui_settings", {})
    if ui:
        data["ui_settings"] = ui
