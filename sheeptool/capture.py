"""捕获与输入层：定位微信小程序窗口、截图、模拟点击。

仅使用 Win32 公开接口（PrintWindow / BitBlt / SendInput），
不注入 DLL、不读写目标进程内存。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time

import cv2
import numpy as np

try:
    import win32con
    import win32gui
    import win32ui
except ImportError as e:  # pragma: no cover
    raise SystemExit("缺少 pywin32，请先执行: pip install pywin32") from e

PW_RENDERFULLCONTENT = 0x00000002
TITLE_DEFAULT = "羊了个羊"


def enable_dpi_awareness() -> None:
    """避免高 DPI 缩放下截图坐标与系统坐标不一致。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def find_window(title_substr: str = TITLE_DEFAULT) -> int:
    """按标题子串查找可见的顶层窗口，返回句柄。"""
    hits: list[tuple[int, str]] = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        text = win32gui.GetWindowText(hwnd)
        if title_substr in text:
            r = win32gui.GetClientRect(hwnd)
            if r[2] - r[0] > 300 and r[3] - r[1] > 300:
                hits.append((hwnd, text))
        return True

    win32gui.EnumWindows(cb, None)
    if not hits:
        raise RuntimeError(f"未找到标题含「{title_substr}」的窗口，请确认小程序已打开")
    hits.sort(key=lambda h: len(h[1]))
    return hits[0][0]


def _grab_printwindow(hwnd: int) -> np.ndarray | None:
    # PrintWindow 把整个窗口（含标题栏）画进 DC，因此尺寸必须用窗口矩形，
    # 否则图像与屏幕坐标之间会差一个标题栏高度。
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    w, h = r - l, b - t
    if w <= 0 or h <= 0:
        return None
    hdc = win32gui.GetWindowDC(hwnd)
    src = win32ui.CreateDCFromHandle(hdc)
    mem = src.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    try:
        bmp.CreateCompatibleBitmap(src, w, h)
        mem.SelectObject(bmp)
        ok = ctypes.windll.user32.PrintWindow(hwnd, mem.GetSafeHdc(), PW_RENDERFULLCONTENT)
        if not ok:
            return None
        info = bmp.GetInfo()
        bits = bmp.GetBitmapBits(True)
        img = np.frombuffer(bits, dtype=np.uint8).reshape(info["bmHeight"], info["bmWidth"], 4)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    finally:
        mem.DeleteDC()
        src.DeleteDC()
        win32gui.ReleaseDC(hwnd, hdc)
        win32gui.DeleteObject(bmp.GetHandle())


def _grab_screen(hwnd: int) -> np.ndarray | None:
    import mss

    l, t, r, b = win32gui.GetWindowRect(hwnd)
    with mss.mss() as sct:
        shot = sct.grab({"left": l, "top": t, "width": r - l, "height": b - t})
        return cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)


def _usable(img: np.ndarray | None) -> bool:
    if img is None or img.size == 0:
        return False
    return float(img.std()) > 6.0


def grab(hwnd: int | None = None, title: str = TITLE_DEFAULT) -> tuple[np.ndarray, tuple[int, int], int]:
    """截图。返回 (图像, 图像左上角对应的屏幕坐标, 窗口句柄)。

    图像坐标系原点 = 窗口矩形左上角，因此 屏幕坐标 = 原点 + 图像坐标。
    """
    enable_dpi_awareness()
    hwnd = hwnd or find_window(title)
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    ox, oy = l, t
    img = _grab_printwindow(hwnd)
    if not _usable(img):
        img = _grab_screen(hwnd)
    if not _usable(img):
        raise RuntimeError("截图失败：PrintWindow 与屏幕抓取均返回空画面")
    return img, (ox, oy), hwnd


def click(x: int, y: int, hwnd: int | None = None, settle: float = 0.12) -> None:
    """在屏幕绝对坐标 (x, y) 处左键单击一次。"""
    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.02)
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
    time.sleep(0.03)
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP
    time.sleep(settle)


def focus(hwnd: int) -> None:
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.15)
    except Exception:
        pass
