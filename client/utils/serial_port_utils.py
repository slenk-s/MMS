"""COM 串口端口扫描工具

优先使用 pyserial 的 list_ports 进行精确扫描；
若 pyserial 不可用（如打包环境缺失），降级为 Windows registry / /dev/tty* 启发式扫描。
"""

def get_available_com_ports() -> list[str]:
    """返回当前系统可用 COM 端口名称列表，按数字排序。"""
    try:
        import serial.tools.list_ports
        ports = [p.device for p in serial.tools.list_ports.comports()]
        # 按端口号排序：COM3 < COM10 < COM20
        def _sort_key(name: str):
            try:
                # 提取数字部分
                return int("".join(filter(str.isdigit, name)))
            except ValueError:
                return 0
        ports.sort(key=_sort_key)
        return ports
    except ImportError:
        pass

    # pyserial 不可用，尝试 Windows registry 扫描
    if hasattr(__import__("platform"), "system") and __import__("platform").system() == "Windows":
        return _scan_com_ports_win32()

    # 其他系统（Linux/macOS）：列举 /dev/tty*
    return _scan_com_ports_posix()


def _scan_com_ports_win32() -> list[str]:
    """通过 Windows registry 扫描 COM 端口（不依赖 pyserial）"""
    import re
    try:
        import winreg
        ports = []
        # 枚举 HKEY_LOCAL_MACHINE\HARDWARE\DEVICEMAP\SERIALCOMM
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DEVICEMAP\SERIALCOMM") as key:
                i = 0
                while True:
                    try:
                        _, value, _ = winreg.EnumValue(key, i)
                        if isinstance(value, str) and value.startswith("COM"):
                            ports.append(value)
                        i += 1
                    except OSError:
                        break
        except FileNotFoundError:
            pass

        if not ports:
            # 兜底：COM1 ~ COM256 启发式
            ports = [f"COM{i}" for i in range(1, 257)]
        return sorted(ports, key=lambda p: int("".join(filter(str.isdigit, p))))
    except ImportError:
        return [f"COM{i}" for i in range(1, 17)]


def _scan_com_ports_posix() -> list[str]:
    """Linux/macOS 扫描 /dev/ttyUSB*、/dev/ttyACM*、/dev/ttyS*"""
    import os
    import glob
    ports = set()
    for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyS*"):
        ports.update(os.path.basename(p) for p in glob.glob(pattern))
    return sorted(ports)
