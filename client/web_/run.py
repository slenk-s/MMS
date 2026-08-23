"""
Web 查询服务启动脚本（v2.5 - HTTPS + HTTP到HTTPS 重定向）
在任何目录下运行：python web_/run.py
功能：
  1. HTTPS 服务监听（默认 0.0.0.0:8000，自签名证书）
  2. HTTP 请求自动 301 重定向到 HTTPS（默认 0.0.0.0:8001）
"""
import os
import sys
import socket
import logging
import threading

# ---------- 打包无控制台模式：重定向 stdout/stderr ----------
# PyInstaller --windowed 模式下使用 pythonw.exe，没有标准流
# 需要重定向到日志文件或 devnull，否则 print() 和 uvicorn 日志可能报错
if getattr(sys, "frozen", False):
    _EXE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    _LOG_DIR = os.path.join(_EXE_DIR, "logs")
    os.makedirs(_LOG_DIR, exist_ok=True)
    _LOG_FILE = os.path.join(_LOG_DIR, "web_query.log")
    try:
        _log_fh = open(_LOG_FILE, "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = _log_fh
        else:
            sys.stdout = _log_fh
        if sys.stderr is None:
            sys.stderr = _log_fh
        else:
            sys.stderr = _log_fh
    except Exception:
        # 兜底：重定向到 devnull
        _null = open(os.devnull, "w", encoding="utf-8")
        if sys.stdout is None:
            sys.stdout = _null
        if sys.stderr is None:
            sys.stderr = _null

# Windows 控制台默认 GBK 编码，无法输出 emoji，强制使用 UTF-8
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 确保在 web_ 目录下运行
if getattr(sys, "frozen", False):
    _EXE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    if hasattr(sys, "_MEIPASS"):
        _THIS_DIR = sys._MEIPASS
        _web_subdir = os.path.join(_THIS_DIR, "web_")
        if os.path.isdir(_web_subdir):
            _THIS_DIR = _web_subdir
    else:
        _THIS_DIR = os.path.join(_EXE_DIR, "_internal", "web_")
        if not os.path.isdir(_THIS_DIR):
            _THIS_DIR = os.path.join(_EXE_DIR, "web_")
else:
    _THIS_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(_THIS_DIR)
sys.path.insert(0, _THIS_DIR)

# 确保 client/ 在搜索路径上（utils/logger/app_config/credential_manager 在此）
for _p in [
    os.path.join(os.path.dirname(_THIS_DIR), "client"),
    os.path.join(os.path.dirname(_THIS_DIR)),
]:
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

# 导入统一 config.ini 路径
try:
    from utils.app_config import get_config_path
except Exception:
    try:
        from app_config import get_config_path
    except Exception:
        get_config_path = None

import uvicorn
from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl

def get_lan_ip():
    """获取当前局域网 IP 地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None

def start_mdns(port: int = 8000):
    """注册 mDNS 服务，使 http://hostname.local:port 可被局域网设备解析"""
    try:
        from zeroconf import Zeroconf, ServiceInfo
        hostname = socket.gethostname()
        lan_ip = get_lan_ip()
        if not lan_ip:
            return
        local_hostname = f"{hostname}.local."
        info = ServiceInfo(
            type_="_https._tcp.local.",
            name=f"MMS - {hostname}._https._tcp.local.",
            addresses=[socket.inet_aton(lan_ip)],
            port=port,
            properties={},
            server=local_hostname,
        )
        zc = Zeroconf(interfaces=[lan_ip])
        zc.register_service(info)
        # 保持引用，防止被 GC
        start_mdns._zc = zc
        print(f"  ✓ mDNS 服务已注册: {hostname}.local")
    except ImportError:
        pass
    except (OSError, RuntimeError, ValueError, socket.error) as e:
        print(f"  ⚠ mDNS 注册失败: {e} (不影响服务运行)")
    except Exception as e:
        print(f"  ⚠ mDNS 注册未预期异常: {e} (不影响服务运行)")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1 仅本机访问；需局域网访问时使用 --host 0.0.0.0）")
    parser.add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
    parser.add_argument("--dev", action="store_true", help="开发模式（启用热重载）")
    args, _ = parser.parse_known_args()

    host = args.host
    port = args.port
    is_dev = args.dev or os.getenv("WEB_MMS_DEV", "").lower() in ("1", "true", "yes")

    # ---------- 单实例保护：端口已被占用时直接退出 ----------
    try:
        _check_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _check_sock.settimeout(0.5)
        if _check_sock.connect_ex(("127.0.0.1", port)) == 0:
            print(f"⚠️  端口 {port} 已被占用，Web 服务可能已在运行，本实例退出。")
            _check_sock.close()
            os._exit(0)
        _check_sock.close()
    except Exception:
        pass

    hostname = socket.gethostname()
    print("=" * 50)
    print("[MMS] 物料管理系统 - Web 查询服务正在启动...")
    print(f"[MMS] 服务器监听地址: {host}:{port}")
    print("[MMS] 请使用以下地址在浏览器中访问：")
    print(f"  → https://127.0.0.1:{port}")
    print(f"  → https://localhost:{port}")
    lan_ip = get_lan_ip()
    if lan_ip:
        print(f"  → https://{lan_ip}:{port}    (局域网 IP - 其他设备访问)")
    print(f"  → https://{hostname}.local:{port}    (手机/平板 - mDNS 自动发现)")
    print(f"  → https://{hostname}:{port}         (电脑 - NetBIOS 计算机名)")
    print("=" * 50)

    # 启动 mDNS 服务注册（后台线程）
    t = threading.Thread(target=start_mdns, args=(port,), daemon=True)
    t.start()

    # 检查 config.ini 文件是否存在
    _ini_path = get_config_path() if get_config_path else None
    if not _ini_path or not os.path.isfile(_ini_path):
        print("⚠️  警告：未找到 config.ini 文件，数据库连接将使用默认配置。")
        print(f"   请在以下路径创建 config.ini 文件：{_ini_path or '项目根目录'}")
        print("   需包含 [mysql] 和 [web_query] 节。")
        print("-" * 50)

    # 尝试预检数据库连接
    try:
        from database import db
        db._ensure_conn()
        print("✅ 数据库连接测试通过")
    except (RuntimeError, OSError) as e:
        print(f"❌ 数据库连接测试失败：{e}")
        print("   请检查系统配置并确认 MySQL 服务可访问。")
        print("-" * 50)
    except Exception as e:
        print(f"❌ 数据库连接测试未预期异常：{e}")
        print("-" * 50)

    if is_dev:
        print("🛠️  开发模式：已启用热重载（代码变更自动重启）")
    else:
        print("🏭 生产模式：热重载已禁用，适合长期运行")


    # 加载 SSL 证书（从打包目录或开发目录的 web_/certs/）
    cert_path = None
    key_path = None
    try:
        _certs_candidates = []
        if getattr(sys, "frozen", False):
            _exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            _certs_candidates.extend([
                os.path.join(_exe_dir, "_internal", "web_", "certs"),
                os.path.join(_exe_dir, "web_", "certs"),
            ])
        else:
            _certs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs")
            _certs_candidates.append(_certs_dir)

        for _cd in _certs_candidates:
            _sp = os.path.join(_cd, "server.pem")
            _kp = os.path.join(_cd, "server.key")
            if os.path.isfile(_sp) and os.path.isfile(_kp):
                cert_path = _sp
                key_path = _kp
                break
    except Exception:
        pass

    ssl_port = port
    http_redirect_port = 8001 if port == 8000 else (port + 1)
    use_https = cert_path is not None

    if use_https:
        print("HTTPS 已启用（自签名证书，CA 已安装到系统信任库）")
    else:
        print("警告：未找到 SSL 证书，将降级为纯 HTTP 模式")
        http_redirect_port = None

    # 启动 HTTP 到 HTTPS 重定向服务器（后台线程）
    if http_redirect_port is not None:
        try:
            class RedirectHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(301)
                    self.send_header("Location", "https://" + host + ":" + str(ssl_port) + self.path)
                    self.end_headers()

                def do_POST(self):
                    self.send_response(301)
                    self.send_header("Location", "https://" + host + ":" + str(ssl_port) + self.path)
                    self.end_headers()

                def log_message(self, format, *args):
                    pass

            http_server = HTTPServer((host, http_redirect_port), RedirectHandler)
            http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
            http_thread.start()
            print("HTTP 重定向服务已启动: http://" + host + ":" + str(http_redirect_port) + " -> https://" + host + ":" + str(ssl_port))
        except OSError as e:
            print("HTTP 重定向端口 " + str(http_redirect_port) + " 被占用，跳过")
            http_redirect_port = None
        except Exception as e:
            print("HTTP 重定向服务启动失败: " + str(e))
            http_redirect_port = None

    if use_https:
        print("=" * 50)
        print("请使用以下地址在浏览器中访问（HTTPS 安全连接）：")
        print("  -> https://127.0.0.1:" + str(ssl_port))
        print("  -> https://localhost:" + str(ssl_port))
        _lan_ip2 = get_lan_ip()
        if _lan_ip2:
            print("  -> https://" + _lan_ip2 + ":" + str(ssl_port) + "    (局域网 IP)")
        print("  -> https://" + hostname + ".local:" + str(ssl_port) + "    (手机/平板)")
        print("  -> https://" + hostname + ":" + str(ssl_port) + "         (电脑)")
        if http_redirect_port:
            print("  HTTP 请求将自动跳转到 HTTPS: http://" + host + ":" + str(http_redirect_port))
        print("=" * 50)

    from app import app as _app

    # Windows asyncio ??????????????????
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)

    if use_https:
        uvicorn.run(
            _app,
            host=host,
            port=ssl_port,
            reload=is_dev,
            log_level="info",
            ssl_certfile=cert_path,
            ssl_keyfile=key_path,
        )
    else:
        uvicorn.run(
            _app,
            host=host,
            port=port,
            reload=is_dev,
            log_level="info",
        )
