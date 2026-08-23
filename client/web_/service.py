"""
Windows Service 包装FastAPI 应用注册Windows 服务，实现开机自启后台运行崩溃自动重
用法（编译后）：
    MMSWebQuery.exe install     -- 注册服务
    MMSWebQuery.exe start       -- 启动服务
    MMSWebQuery.exe stop        -- 停止服务
    MMSWebQuery.exe remove      -- 卸载服务
    MMSWebQuery.exe debug       -- 前台调试模式
"""
import os
import sys
import threading
import logging
import configparser
from logging.handlers import RotatingFileHandler


def _trace(msg):
    """写入调试追踪文件（exe 运行后可用于定位问题）"""
    try:
        with open(os.path.join(os.path.dirname(sys.executable), "_trace.log"), "a", encoding="utf-8") as f:
            f.write(msg + "\n")
            f.flush()
    except Exception:
        pass


def _get_base_dir() -> str:
    """返回资源（PyInstaller 时为 sys._MEIPASS，否则为脚本扢在目录）"""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


def _get_exe_dir() -> str:
    """返回 .exe 扢在目录（存放 config.ini 和日志）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return _get_base_dir()


BASE_DIR = _get_base_dir()
EXE_DIR = _get_exe_dir()

_trace(f"[1] frozen={getattr(sys, 'frozen', None)}")
_trace(f"[2] BASE_DIR={BASE_DIR}  EXE_DIR={EXE_DIR}")
_trace(f"[3] __file__={__file__}")
_trace(f"[4] sys.argv={sys.argv}")

# 将资源目录和 client/ 加入模块搜索路径，确保 app 模块可以导入
sys.path.insert(0, BASE_DIR)
_trace(f"[5] sys.path[0]={sys.path[0]}")

# 导入统一 config.ini 路径（优先从 utils.app_config，fallback app_config）
try:
    from utils.app_config import get_config_path
except Exception:
    try:
        from app_config import get_config_path
    except Exception:
        get_config_path = None
_TRACE_INI = get_config_path() if get_config_path else None
_trace(f"[5b] config.ini path={_TRACE_INI}")

# 导入 FastAPI 应用对象（对象导入非 "app:app" 字符串）
import app as _mms_app  # noqa: E402
_trace("[6] app imported OK")

LOG_DIR = os.path.join(EXE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def _setup_logging() -> logging.Logger:
    """配置滚动文件日志"""
    logger = logging.getLogger("MMSWebService")
    logger.setLevel(logging.DEBUG)
    fh = RotatingFileHandler(
        os.path.join(LOG_DIR, "service.log"),
        maxBytes=5_242_880,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(fh)
    return logger


logger = _setup_logging()
_trace("[7] logger setup OK")

# ┢┢ 服务常量 ┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢
SERVICE_NAME = "MMSWebQuery"
SERVICE_DISPLAY_NAME = "[MMS] Web查询服务"
SERVICE_DESCRIPTION = "物料管理系统 Web 查询服务（FastAPI + MySQL），提供领料记录查询接口"


def _get_port() -> int:
    """解析监听端口：命令行 --port > config.ini [web_query] web_query_port > 默认 8000"""
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            try:
                return int(sys.argv[i + 1])
            except ValueError:
                pass
        if arg.startswith("--port="):
            try:
                return int(arg.split("=", 1)[1])
            except ValueError:
                pass

    if get_config_path and os.path.isfile(get_config_path()):
        try:
            cp = configparser.ConfigParser()
            cp.read(get_config_path(), encoding="utf-8-sig")
            return int(cp.get("web_query", "web_query_port", fallback="8000"))
        except (ValueError, configparser.Error):
            pass
    return 8000


PORT = _get_port()

# ┢┢ 入口（在导入 win32 之前处理 debug 模式）─┢┢
if "--debug" in sys.argv or "debug" in sys.argv:
    _trace("[8] entering debug mode")

    def _run_debug():
        _trace("[9] _run_debug started")
        print("=" * 50)
        print("[MMS] 调试模式 - 前台运行")
        print(f"[MMS] 服务器监听地坢: 0.0.0.0:{PORT}")
        print("[MMS] Ctrl+C 停止")
        print("=" * 50)

        _trace("[10] about to import uvicorn")
        import uvicorn  # noqa: PLC0415
        _trace("[11] uvicorn imported OK")

        uvicorn.run(
            _mms_app.app,
            host="0.0.0.0",
            port=PORT,
            log_level="info",
            reload=False,
        )

    _run_debug()
    raise SystemExit(0)


# ┢┢ 以下仅在服务模式 / 命令行管理模式下执行 ┢┢
import win32serviceutil
import win32service
import win32event
import servicemanager
import pywintypes

# ┢┢ 服务实现 ┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢
class MMSWebService(win32serviceutil.ServiceFramework):
    """MMS FastAPI 应用Windows 服务实现"""

    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = SERVICE_DESCRIPTION

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self._server = None
        self._server_thread = None

    @staticmethod
    def _find_ini_file() -> str | None:
        if get_config_path and os.path.isfile(get_config_path()):
            return get_config_path()
        return None

    def SvcDoRun(self):
        """SCM 启动服务时调用：在后台线程运行 uvicorn，等待停止信号"""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (SERVICE_DISPLAY_NAME, ""),
        )
        logger.info("Service starting...")

        ini_path = self._find_ini_file()
        if ini_path:
            logger.info("Using config.ini file: %s", ini_path)
        else:
            logger.warning("No config.ini file found. Database will use defaults.")

        self._server_thread = threading.Thread(
            target=self._run_uvicorn,
            daemon=True,
            name="uvicorn-server",
        )
        self._server_thread.start()

        win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)

        logger.info("Service stopped.")
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STOPPED,
            (SERVICE_DISPLAY_NAME, ""),
        )

    def SvcStop(self):
        """SCM 停止服务时调用：优雅关闭 uvicorn"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        logger.info("Service stopping...")

        if self._server is not None:
            self._server.should_exit = True

        win32event.SetEvent(self.hWaitStop)

        if self._server_thread is not None and self._server_thread.is_alive():
            self._server_thread.join(timeout=30)

        logger.info("Service stopped gracefully.")

    def _run_uvicorn(self):
        """在后台线程中运行 uvicorn 服务"""
        os.chdir(EXE_DIR)
        sys.path.insert(0, BASE_DIR)

        import uvicorn  # noqa: PLC0415
        from uvicorn import Config, Server  # noqa: PLC0415

        config = Config(
            _mms_app.app,
            host="0.0.0.0",
            port=PORT,
            log_level="info",
            reload=False,
            workers=1,
            log_config=None,
        )
        self._server = Server(config)
        logger.info("Uvicorn starting on 0.0.0.0:%d", PORT)
        try:
            self._server.run()
        except (OSError, RuntimeError, ValueError) as e:
            logger.exception("Uvicorn server failed: %s", e)
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_ERROR_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (SERVICE_DISPLAY_NAME, f"Uvicorn error: {e}"),
            )
            win32event.SetEvent(self.hWaitStop)
        except Exception as e:
            logger.exception("Uvicorn server unexpected error: %s", e)
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_ERROR_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (SERVICE_DISPLAY_NAME, f"Uvicorn unexpected error: {e}"),
            )
            win32event.SetEvent(self.hWaitStop)


if __name__ == "__main__":
    _trace("[12] __main__ reached")
    if len(sys.argv) == 1:
        _trace("[13] no args, trying SCM (1063 handler)")
        try:
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(MMSWebService)
            servicemanager.StartServiceCtrlDispatcher()
        except pywintypes.error as e:
            if e.winerror == 1063:
                _trace("[15] error 1063 -> auto start server in foreground")
                import uvicorn
                import threading

                server_config = uvicorn.Config(
                    _mms_app.app,
                    host="0.0.0.0",
                    port=PORT,
                    log_level="info",
                    reload=False,
                )
                server = uvicorn.Server(server_config)
                server_thread = threading.Thread(target=server.run, daemon=True)
                server_thread.start()

                try:
                    import ctypes
                    import webbrowser
                    webbrowser.open(f"http://localhost:{PORT}")
                    ctypes.windll.user32.MessageBoxW(
                        0,
                        "MMS Web Query server is running.\n\n"
                        f"Query:  http://localhost:{PORT}\n"
                        f"Config: http://localhost:{PORT}/config\n\n"
                        "Click OK to STOP the server.",
                        "[MMS] Web Query Service",
                        0x40,
                    )
                except Exception:
                    pass
                server.should_exit = True
                server_thread.join(timeout=3)
            else:
                raise
    else:
        _trace("[14] args present, HandleCommandLine")
        win32serviceutil.HandleCommandLine(MMSWebService)
