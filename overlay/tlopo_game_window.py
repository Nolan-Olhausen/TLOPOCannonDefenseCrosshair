"""
Locate the TLOPO game client window and read its **client** rectangle in screen pixels.

Aligned with Brewing ``tlopo_client/window.py`` (same defaults and mss/DPI alignment idea),
kept local so this overlay runs without the Brewing tree on ``PYTHONPATH``.
"""

from __future__ import annotations

import ctypes
import re
import sys
import threading
from ctypes import wintypes
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

try:
    import win32api  # type: ignore
    import win32con  # type: ignore
    import win32gui  # type: ignore
    import win32process  # type: ignore

    WIN32_OK = True
except ImportError:
    win32api = None  # type: ignore
    win32con = None  # type: ignore
    win32gui = None  # type: ignore
    win32process = None  # type: ignore
    WIN32_OK = False

try:
    import psutil
except ImportError:
    psutil = None

DEFAULT_GAME_WINDOW_TITLE = "The Legend of Pirates Online [BETA]"

DWMWA_EXTENDED_FRAME_BOUNDS = 9
_dwmapi = None
try:
    _dwmapi = ctypes.WinDLL("dwmapi")
except Exception:
    _dwmapi = None


def enable_process_dpi_awareness() -> None:
    if not WIN32_OK:
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _get_extended_frame_bounds(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    if not _dwmapi:
        return None
    rect = wintypes.RECT()
    hr = _dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
        ctypes.byref(rect),
        ctypes.sizeof(rect),
    )
    if hr == 0:
        return rect.left, rect.top, rect.right, rect.bottom
    return None


def _compile_title_patterns(keywords: Iterable[str]) -> list[re.Pattern[str]]:
    return [re.compile(re.escape(k), re.IGNORECASE) for k in keywords]


def _client_area_pixels(hwnd: int) -> int:
    if not WIN32_OK:
        return 0
    try:
        l, t, r, b = win32gui.GetClientRect(hwnd)
        return max(0, r - l) * max(0, b - t)
    except Exception:
        return 0


def _title_match_score(title: str) -> int:
    t = title.lower()
    score = 0
    if "[beta]" in t:
        score += 500
    if "the legend of pirates online" in t:
        score += 200
    if "tlopo" in t:
        score += 50
    return score


class TlopoGameWindow:
    """Find TLOPO and expose client rect in screen coordinates (for overlays)."""

    def __init__(
        self,
        proc_names: Iterable[str] = ("tlopo.exe",),
        title_keywords: Iterable[str] = (
            DEFAULT_GAME_WINDOW_TITLE,
            "The Legend of Pirates Online",
            "TLOPO",
        ),
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.proc_names = tuple(n.lower() for n in proc_names)
        self._title_patterns = _compile_title_patterns(title_keywords)
        self._log = log or (lambda _m: None)
        self._lock = threading.RLock()
        self._hwnd: Optional[int] = None

    def find_window(self) -> bool:
        if not WIN32_OK:
            self._log("pywin32 not installed; cannot find TLOPO window.")
            with self._lock:
                self._hwnd = None
            return False

        hwnd: Optional[int] = None
        candidates: list[tuple[int, str]] = []

        if psutil is not None and self.proc_names:
            try:
                pids: list[int] = []
                for p in psutil.process_iter(["pid", "name"]):
                    name = (p.info.get("name") or "").lower()
                    if name in self.proc_names:
                        pids.append(int(p.info["pid"]))
                candidates = self._enumerate_windows_for_pids(pids)
            except Exception as e:
                self._log(f"psutil process scan failed: {e}")

        if not candidates:
            candidates = self._enumerate_windows_by_title()

        if candidates:
            hwnd = self._pick_best_hwnd(candidates)

        with self._lock:
            if hwnd and win32gui.IsWindow(hwnd):
                self._hwnd = hwnd
                return True
            self._hwnd = None
            return False

    def get_hwnd(self) -> Optional[int]:
        with self._lock:
            return self._hwnd

    def get_window_title(self) -> str:
        if not WIN32_OK:
            return ""
        with self._lock:
            h = self._hwnd
        if not h:
            return ""
        try:
            return (win32gui.GetWindowText(h) or "").strip()
        except Exception:
            return ""

    def is_valid(self) -> bool:
        if not WIN32_OK:
            return False
        with self._lock:
            h = self._hwnd
        if not h:
            return False
        try:
            return bool(
                win32gui.IsWindow(h)
                and win32gui.IsWindowVisible(h)
                and not win32gui.IsIconic(h)
            )
        except Exception:
            return False

    def get_client_rect(self) -> Optional[Tuple[int, int, int, int]]:
        if not WIN32_OK:
            return None
        with self._lock:
            h = self._hwnd
        if not h:
            return None
        try:
            _l, _t, r_rel, b_rel = win32gui.GetClientRect(h)
            top_left = win32gui.ClientToScreen(h, (0, 0))
            l, t = top_left[0], top_left[1]
            return l, t, l + (r_rel - _l), t + (b_rel - _t)
        except Exception:
            return None

    def get_client_rect_mss_aligned(self) -> Optional[Tuple[int, int, int, int]]:
        """Match Win32 client origin to mss bitmap size (Hi-DPI drift fix)."""
        r = self.get_client_rect()
        if not r:
            return None
        l, t, ri, bo = r
        w, h = int(ri - l), int(bo - t)
        if w < 1 or h < 1:
            return r
        try:
            import mss  # type: ignore
        except ImportError:
            return r
        if sys.platform == "win32":
            try:
                from mss import windows as _mss_win  # type: ignore[import-untyped]

                _mss_win.MSS._set_dpi_awareness = lambda _self: None  # type: ignore[method-assign]
            except Exception:
                pass
        try:
            with mss.mss() as sct:
                shot = sct.grab({"left": int(l), "top": int(t), "width": w, "height": h})
            sw, sh = int(shot.size[0]), int(shot.size[1])
        except Exception:
            return r
        if sw < 1 or sh < 1:
            return r
        if sw == w and sh == h:
            return r
        return (l, t, l + sw, t + sh)

    def get_window_info(self) -> Optional[Dict[str, Any]]:
        if not WIN32_OK:
            return None
        with self._lock:
            hwnd = self._hwnd
        if not hwnd or not win32gui.IsWindow(hwnd):
            return None
        try:
            info: Dict[str, Any] = {}
            client_rect = self.get_client_rect()
            if client_rect:
                cl, ct, cr, cb = client_rect
                info["client"] = {
                    "left": cl,
                    "top": ct,
                    "right": cr,
                    "bottom": cb,
                    "width": cr - cl,
                    "height": cb - ct,
                }
            try:
                title = win32gui.GetWindowText(hwnd) or ""
                info["window"] = {"handle": hwnd, "title": title}
            except Exception:
                info["window"] = {"handle": hwnd}
            return info
        except Exception:
            return None

    def _enumerate_windows_for_pids(self, pids: list[int]) -> list[tuple[int, str]]:
        if not pids or not WIN32_OK:
            return []
        pset = set(pids)
        found: list[tuple[int, str]] = []

        def enum_handler(hwnd: int, _lp) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid not in pset:
                    return True
                title = (win32gui.GetWindowText(hwnd) or "").strip()
                if title and any(p.search(title) for p in self._title_patterns):
                    found.append((hwnd, title))
            except Exception:
                pass
            return True

        try:
            win32gui.EnumWindows(enum_handler, None)
        except Exception:
            return []
        return found

    def _enumerate_windows_by_title(self) -> list[tuple[int, str]]:
        if not WIN32_OK:
            return []
        found: list[tuple[int, str]] = []

        def enum_handler(hwnd: int, _lp) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            try:
                title = (win32gui.GetWindowText(hwnd) or "").strip()
                if title and any(p.search(title) for p in self._title_patterns):
                    found.append((hwnd, title))
            except Exception:
                pass
            return True

        try:
            win32gui.EnumWindows(enum_handler, None)
        except Exception:
            return []
        return found

    def _pick_best_hwnd(self, candidates: list[tuple[int, str]]) -> Optional[int]:
        if not candidates or not WIN32_OK:
            return None
        ranked: list[tuple[tuple[int, int], int, str]] = []
        for hwnd, title in candidates:
            if not win32gui.IsWindow(hwnd):
                continue
            area = _client_area_pixels(hwnd)
            if area < 10_000:
                continue
            ts = _title_match_score(title)
            ranked.append(((ts, area), hwnd, title))
        if not ranked:
            for hwnd, title in candidates:
                if win32gui.IsWindow(hwnd):
                    return hwnd
            return None
        ranked.sort(key=lambda x: x[0], reverse=True)
        best = ranked[0]
        self._log(f"Picked game window: '{best[2]}' (score={best[0][0]}, client_px²={best[0][1]})")
        return best[1]


__all__ = ["TlopoGameWindow", "DEFAULT_GAME_WINDOW_TITLE", "enable_process_dpi_awareness"]
