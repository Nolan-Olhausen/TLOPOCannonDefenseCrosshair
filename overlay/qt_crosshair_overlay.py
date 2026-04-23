"""
Minimal Qt overlay for Cannon Defense.

Only supports screen-mode vertical movement with 3 speed sections.
Crosshair is always rendered as a small red circle.
"""

from __future__ import annotations

import ctypes
import math
import sys
from ctypes import wintypes
from typing import Any, Callable, Dict, Optional, Tuple

import tkinter as tk

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

LogFn = Callable[[str], None]
ClientRectFn = Callable[[], Optional[Tuple[int, int, int, int]]]
GameHwndFn = Callable[[], Optional[int]]

VK_RBUTTON = 0x02
WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
RIDEV_INPUTSINK = 0x00000100
RIDEV_REMOVE = 0x00000001
MOUSE_MOVE_ABSOLUTE = 0x01

HWND_TOPMOST = -1
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

_USER32 = ctypes.windll.user32 if sys.platform == "win32" else None


class _RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", wintypes.WPARAM),
    ]


class _RAWMOUSE(ctypes.Structure):
    _fields_ = [
        ("usFlags", wintypes.USHORT),
        ("_pad", wintypes.USHORT),
        ("ulButtons", wintypes.DWORD),
        ("ulRawButtons", wintypes.DWORD),
        ("lLastX", wintypes.LONG),
        ("lLastY", wintypes.LONG),
        ("ulExtraInformation", wintypes.DWORD),
    ]


class _RAWINPUT(ctypes.Structure):
    _fields_ = [("header", _RAWINPUTHEADER), ("mouse", _RAWMOUSE)]


class _RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]


def _vertical_aim_span(ch: int) -> float:
    return max(1.0, float(max(1, ch) - 1))


def _vertical_aim_y_bounds(s: Dict[str, Any], ch: int) -> Tuple[float, float]:
    span = _vertical_aim_span(ch)
    r_lo = max(0.0, min(1.0, float(s.get("vertical_aim_min_ratio", 0.13))))
    r_hi = max(0.0, min(1.0, float(s.get("vertical_aim_max_ratio", 0.34))))
    if r_lo > r_hi:
        r_lo, r_hi = r_hi, r_lo
    y_min, y_max = r_lo * span, r_hi * span
    if y_max - y_min < 4.0:
        return 0.0, span
    return y_min, y_max


def _clamp_aim_y(s: Dict[str, Any], ch: int, y: float) -> float:
    y_lo, y_hi = _vertical_aim_y_bounds(s, ch)
    return max(y_lo, min(y_hi, float(y)))


def _section_multiplier_for_branch(
    s: Dict[str, Any], aim_y: float, ch: int, branch: str
) -> float:
    span = _vertical_aim_span(ch)
    r = max(0.0, min(1.0, float(aim_y) / span if span > 0 else 0.0))
    rmin = max(0.0, min(1.0, float(s.get("vertical_aim_min_ratio", 0.13))))
    rmax = max(0.0, min(1.0, float(s.get("vertical_aim_max_ratio", 0.34))))
    if rmax <= rmin:
        return 1.0
    t = (max(rmin, min(rmax, r)) - rmin) / (rmax - rmin)
    pref = "top_branch" if str(branch).lower() == "top" else "bottom_branch"
    s1 = max(0.0, min(1.0, float(s.get(f"{pref}_section_split1", s.get("vertical_section_split1", 0.3333)))))
    s2 = max(0.0, min(1.0, float(s.get(f"{pref}_section_split2", s.get("vertical_section_split2", 0.6667)))))
    if s2 < s1:
        s1, s2 = s2, s1
    top = max(0.05, min(4.0, float(s.get(f"{pref}_section_sens_top", s.get("vertical_section_speed_top", 1.0)))))
    mid = max(0.05, min(4.0, float(s.get(f"{pref}_section_sens_mid", s.get("vertical_section_speed_mid", 1.0))))
    )
    bot = max(0.05, min(4.0, float(s.get(f"{pref}_section_sens_bottom", s.get("vertical_section_speed_bottom", 1.0)))))
    if pref == "top_branch":
        s3 = max(0.0, min(1.0, float(s.get("top_branch_section_split3", 0.8750))))
        if s3 < s2:
            s3 = s2
        low = max(0.05, min(4.0, float(s.get("top_branch_section_sens_low", bot))))
        if t < s1:
            return top
        if t < s2:
            return mid
        if t < s3:
            return bot
        return low
    if t < s1:
        return top
    if t < s2:
        return mid
    return bot


def _rmb_held() -> bool:
    if sys.platform != "win32":
        return False
    return (ctypes.windll.user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000) != 0


def _cursor_screen() -> Optional[Tuple[int, int]]:
    if sys.platform != "win32" or _USER32 is None:
        return None
    class _POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]
    pt = _POINT()
    if not _USER32.GetCursorPos(ctypes.byref(pt)):
        return None
    return int(pt.x), int(pt.y)


def _cursor_client_y(hwnd: Optional[int]) -> Optional[float]:
    if hwnd is None or sys.platform != "win32" or _USER32 is None:
        return None
    pt = _cursor_screen()
    if not pt:
        return None
    class _POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]
    cpt = _POINT(int(pt[0]), int(pt[1]))
    if not _USER32.ScreenToClient(wintypes.HWND(int(hwnd)), ctypes.byref(cpt)):
        return None
    return float(cpt.y)


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _set_native_window_geometry(hwnd: int, left: int, top: int, width: int, height: int) -> bool:
    if sys.platform != "win32" or hwnd == 0 or width < 1 or height < 1:
        return False
    ok = ctypes.windll.user32.SetWindowPos(
        wintypes.HWND(hwnd),
        wintypes.HWND(HWND_TOPMOST),
        int(left),
        int(top),
        int(width),
        int(height),
        int(SWP_NOACTIVATE | SWP_SHOWWINDOW),
    )
    return bool(ok)


class _CrosshairSurface(QWidget):
    def __init__(
        self,
        get_client_rect: ClientRectFn,
        get_game_hwnd: GameHwndFn,
        settings_ref: Callable[[], Dict[str, Any]],
        log: LogFn,
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput,
        )
        self._get_client_rect = get_client_rect
        self._get_game_hwnd = get_game_hwnd
        self._settings_ref = settings_ref
        self._log = log
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        if sys.platform == "win32":
            self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setAutoFillBackground(False)

        self._aim_y: Optional[float] = None
        self._last_mouse_y: Optional[float] = None
        self._raw_dy_accum: float = 0.0
        self._raw_input_registered: bool = False
        self._game_cw = 1
        self._game_ch = 1
        self._active_branch = "top"
        self._was_in_top_trigger = False
        self._was_in_bottom_trigger = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def _update_branch_trigger(self, ratio: float, s: Dict[str, Any]) -> None:
        r = max(0.0, min(1.0, float(ratio)))
        tmin = float(s.get("top_branch_trigger_min", 0.1325))
        tmax = float(s.get("top_branch_trigger_max", 0.1400))
        bmin = float(s.get("bottom_branch_trigger_min", 0.3350))
        bmax = float(s.get("bottom_branch_trigger_max", 0.3440))
        if tmax < tmin:
            tmin, tmax = tmax, tmin
        if bmax < bmin:
            bmin, bmax = bmax, bmin
        in_top = tmin <= r <= tmax
        in_bottom = bmin <= r <= bmax
        if in_top and not self._was_in_top_trigger:
            self._active_branch = "top"
        if in_bottom and not self._was_in_bottom_trigger:
            self._active_branch = "bottom"
        self._was_in_top_trigger = in_top
        self._was_in_bottom_trigger = in_bottom

    def settings(self) -> Dict[str, Any]:
        return self._settings_ref()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._register_raw_mouse()

    def hideEvent(self, event) -> None:  # type: ignore[override]
        self._unregister_raw_mouse()
        super().hideEvent(event)

    def nativeEvent(self, eventType, message):  # type: ignore[no-untyped-def]
        if sys.platform != "win32" or _USER32 is None or not self._raw_input_registered:
            return super().nativeEvent(eventType, message)
        try:
            et = bytes(eventType)
        except TypeError:
            et = eventType if isinstance(eventType, (bytes, bytearray)) else b""
        if et not in (b"windows_generic_MSG", b"windows_dispatch_MSG"):
            return super().nativeEvent(eventType, message)
        msg = ctypes.wintypes.MSG.from_address(int(message))
        if msg.message != WM_INPUT:
            return super().nativeEvent(eventType, message)
        pcb_size = wintypes.UINT(0)
        hdr_sz = ctypes.sizeof(_RAWINPUTHEADER)
        hrinp = wintypes.HANDLE(msg.lParam)
        _USER32.GetRawInputData(hrinp, RID_INPUT, None, ctypes.byref(pcb_size), hdr_sz)
        if pcb_size.value == 0:
            return True, 0
        buf = (ctypes.c_ubyte * int(pcb_size.value))()
        pcb2 = wintypes.UINT(pcb_size.value)
        _USER32.GetRawInputData(hrinp, RID_INPUT, ctypes.byref(buf), ctypes.byref(pcb2), hdr_sz)
        raw = ctypes.cast(ctypes.addressof(buf), ctypes.POINTER(_RAWINPUT)).contents
        if raw.header.dwType == RIM_TYPEMOUSE and (raw.mouse.usFlags & MOUSE_MOVE_ABSOLUTE) == 0 and _rmb_held():
            self._raw_dy_accum += float(raw.mouse.lLastY)
        return True, 0

    def _register_raw_mouse(self) -> None:
        if sys.platform != "win32" or _USER32 is None or self._raw_input_registered:
            return
        wid = int(self.winId())
        if wid == 0:
            return
        rid = _RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, wintypes.HWND(wid))
        self._raw_input_registered = bool(
            _USER32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid))
        )
        if self._raw_input_registered:
            self._log("Using Raw Input for vertical aim.")

    def _unregister_raw_mouse(self) -> None:
        if sys.platform != "win32" or _USER32 is None:
            return
        if self._raw_input_registered:
            rid = _RAWINPUTDEVICE(0x01, 0x02, RIDEV_REMOVE, wintypes.HWND(0))
            _USER32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid))
        self._raw_input_registered = False
        self._raw_dy_accum = 0.0

    def _anchor_y(self, ch: int) -> float:
        s = self.settings()
        ratio = max(0.0, min(1.0, float(s.get("vertical_anchor_ratio", 0.15))))
        return _clamp_aim_y(s, ch, ratio * float(ch - 1))

    def reset_vertical_to_anchor(self) -> None:
        rect = self._get_client_rect()
        if not rect:
            return
        ch = int(rect[3] - rect[1])
        self._aim_y = self._anchor_y(ch)

    def set_vertical_ratio(self, ratio: float) -> bool:
        rect = self._get_client_rect()
        if not rect:
            return False
        ch = int(rect[3] - rect[1])
        span = _vertical_aim_span(ch)
        self._aim_y = _clamp_aim_y(self.settings(), ch, max(0.0, min(1.0, float(ratio))) * span)
        self.update()
        return True

    def get_vertical_aim_snapshot(self) -> Optional[Dict[str, Any]]:
        if self._aim_y is None:
            return None
        rect = self._get_client_rect()
        if not rect:
            return None
        ch = int(rect[3] - rect[1])
        span = _vertical_aim_span(ch)
        s = self.settings()
        y_lo, y_hi = _vertical_aim_y_bounds(s, ch)
        rmin = float(s.get("vertical_aim_min_ratio", 0.0))
        rmax = float(s.get("vertical_aim_max_ratio", 1.0))
        ratio = float(self._aim_y) / span if span > 0 else 0.0
        t_band = (max(rmin, min(rmax, ratio)) - rmin) / (rmax - rmin) if rmax > rmin else 0.0
        return {
            "ratio": ratio,
            "t_band": t_band,
            "aim_y": float(self._aim_y),
            "ch": ch,
            "span": span,
            "clamp_y_min": y_lo,
            "clamp_y_max": y_hi,
        }

    def _tick(self) -> None:
        rect = self._get_client_rect()
        if not rect:
            return
        l, t, r, b = rect
        cw, ch = int(r - l), int(b - t)
        if cw < 8 or ch < 8:
            return
        self._game_cw, self._game_ch = cw, ch
        hid = int(self.winId())
        if sys.platform == "win32" and hid:
            if not _set_native_window_geometry(hid, l, t, cw, ch):
                self.setGeometry(l, t, cw, ch)
        else:
            self.setGeometry(l, t, cw, ch)

        s = self.settings()
        sens = float(s.get("vertical_sensitivity", 1.0))
        raw_scale = max(0.02, min(2.0, float(s.get("vertical_raw_scale", 0.32))))
        baseline_h = max(1.0, float(s.get("vertical_baseline_client_height", 1050.0)))
        size_scale = max(0.2, min(5.0, float(ch) / baseline_h))
        raw_scale_eff = raw_scale * size_scale
        if self._aim_y is None:
            self._aim_y = self._anchor_y(ch)
        span = _vertical_aim_span(ch)
        self._update_branch_trigger(float(self._aim_y) / span if span > 0 else 0.0, s)

        if self._raw_input_registered:
            if _rmb_held() and self._raw_dy_accum != 0.0:
                remaining = float(self._raw_dy_accum)
                guard = 0
                while abs(remaining) > 1e-6 and guard < 4096:
                    if bool(s.get("vertical_speed_use_sections", True)):
                        self._update_branch_trigger(float(self._aim_y) / span if span > 0 else 0.0, s)
                        m = _section_multiplier_for_branch(s, float(self._aim_y), ch, self._active_branch)
                        gain = max(1e-6, abs(raw_scale_eff * m))
                    else:
                        m = sens
                        gain = max(1e-6, abs(raw_scale_eff * m))
                    max_step = max(0.05, 0.20 / gain)
                    step_mag = min(abs(remaining), max_step)
                    step = step_mag if remaining > 0.0 else -step_mag
                    self._aim_y += step * raw_scale_eff * m
                    self._aim_y = _clamp_aim_y(s, ch, float(self._aim_y))
                    remaining -= step
                    guard += 1
                self._raw_dy_accum = 0.0
            elif not _rmb_held():
                self._raw_dy_accum = 0.0
        else:
            my = _cursor_client_y(self._get_game_hwnd())
            if my is not None:
                if self._last_mouse_y is not None and _rmb_held():
                    remaining = float(my - self._last_mouse_y)
                    guard = 0
                    while abs(remaining) > 1e-6 and guard < 4096:
                        if bool(s.get("vertical_speed_use_sections", True)):
                            self._update_branch_trigger(float(self._aim_y) / span if span > 0 else 0.0, s)
                            m = _section_multiplier_for_branch(s, float(self._aim_y), ch, self._active_branch)
                            gain = max(1e-6, abs(m))
                        else:
                            m = sens
                            gain = max(1e-6, abs(m))
                        max_step = max(0.05, 0.20 / gain)
                        step_mag = min(abs(remaining), max_step)
                        step = step_mag if remaining > 0.0 else -step_mag
                        self._aim_y += step * m * size_scale
                        self._aim_y = _clamp_aim_y(s, ch, float(self._aim_y))
                        remaining -= step
                        guard += 1
                self._last_mouse_y = my
            else:
                self._last_mouse_y = None
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        s = self.settings()
        w_q, h_q = max(1, self.width()), max(1, self.height())
        gc = max(1, int(getattr(self, "_game_cw", w_q)))
        gh = max(1, int(getattr(self, "_game_ch", h_q)))
        aim = float(self._aim_y if self._aim_y is not None else self._anchor_y(gh))
        span = max(1.0, float(gh - 1))
        r_lin = aim / span
        cx = (gc / 2.0) * (w_q / float(gc))
        rmin = float(s.get("vertical_aim_min_ratio", 0.13))
        rmax = float(s.get("vertical_aim_max_ratio", 0.34))

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))

        if bool(s.get("vertical_speed_use_sections", True)) and bool(s.get("vertical_section_overlay", True)):
            # Draw section zones in a narrower band around the reticle area,
            # instead of stretching across the entire screen width.
            band_w = int(max(25, min(50, round(w_q * 0.28))))
            band_x = int(max(0, min(w_q - band_w, round(cx - (band_w / 2.0)))))
            pref = "top_branch" if self._active_branch == "top" else "bottom_branch"
            s1 = max(0.0, min(1.0, float(s.get(f"{pref}_section_split1", s.get("vertical_section_split1", 0.3333)))))
            s2 = max(0.0, min(1.0, float(s.get(f"{pref}_section_split2", s.get("vertical_section_split2", 0.6667)))))
            if s2 < s1:
                s1, s2 = s2, s1
            y0 = (rmin * span) * (h_q / float(gh))
            y1 = ((rmin + (rmax - rmin) * s1) * span) * (h_q / float(gh))
            y2 = ((rmin + (rmax - rmin) * s2) * span) * (h_q / float(gh))
            if self._active_branch == "top":
                s3 = max(0.0, min(1.0, float(s.get("top_branch_section_split3", 0.8750))))
                if s3 < s2:
                    s3 = s2
                y3 = ((rmin + (rmax - rmin) * s3) * span) * (h_q / float(gh))
                y4 = (rmax * span) * (h_q / float(gh))
                top_col = QColor(160, 90, 230, 14)   # purple
                mid_col = QColor(90, 210, 210, 14)   # cyan
                bot_col = QColor(120, 220, 120, 14)  # green
                low_col = QColor(240, 150, 80, 14)   # orange
                if y0 < y1:
                    p.fillRect(band_x, int(y0), band_w, int(y1 - y0), top_col)
                if y1 < y2:
                    p.fillRect(band_x, int(y1), band_w, int(y2 - y1), mid_col)
                if y2 < y3:
                    p.fillRect(band_x, int(y2), band_w, int(y3 - y2), bot_col)
                if y3 < y4:
                    p.fillRect(band_x, int(y3), band_w, int(y4 - y3), low_col)
            else:
                y3 = (rmax * span) * (h_q / float(gh))
                top_col = QColor(80, 140, 220, 14)   # blue
                mid_col = QColor(220, 180, 70, 14)   # yellow
                bot_col = QColor(220, 100, 100, 14)  # red
                if y0 < y1:
                    p.fillRect(band_x, int(y0), band_w, int(y1 - y0), top_col)
                if y1 < y2:
                    p.fillRect(band_x, int(y1), band_w, int(y2 - y1), mid_col)
                if y2 < y3:
                    p.fillRect(band_x, int(y2), band_w, int(y3 - y2), bot_col)
        cy = (r_lin * span) * (h_q / float(gh))

        # Optional right-side reticle attachment: 1 horizontal + 3 vertical crossing lines.
        if bool(s.get("reticle_right_line_enabled", True)):
            ret_r = 4.0
            h_len = max(0.0, min(600.0, float(s.get("reticle_right_line_length", 70.0))))
            h_dy = max(-400.0, min(400.0, float(s.get("reticle_right_line_y_offset", 0.0))))
            h_gap = max(0.0, min(80.0, float(s.get("reticle_right_line_start_gap", 1.0))))
            rot_deg = max(-180.0, min(180.0, float(s.get("reticle_right_line_rotation_deg", 0.0))))
            rot_rad = math.radians(rot_deg)
            c = math.cos(rot_rad)
            sn = math.sin(rot_rad)

            def _rot(px: float, py: float) -> Tuple[float, float]:
                dx = px - cx
                dy = py - cy
                return cx + (dx * c - dy * sn), cy + (dx * sn + dy * c)

            hx1 = cx + ret_r + h_gap
            hx2 = hx1 + h_len
            hy = cy + h_dy
            guide_pen = QPen(QColor(255, 255, 255, 140))
            guide_pen.setWidth(2)
            p.setPen(guide_pen)
            if 0 <= hy <= h_q and hx2 >= 0 and hx1 <= w_q:
                h1x, h1y = _rot(hx1, hy)
                h2x, h2y = _rot(hx2, hy)
                p.drawLine(int(h1x), int(h1y), int(h2x), int(h2y))

                pos1 = max(0.0, min(600.0, float(s.get("reticle_vline1_pos", 18.0))))
                len1 = max(0.0, min(400.0, float(s.get("reticle_vline1_len", 16.0))))
                pos2 = max(0.0, min(600.0, float(s.get("reticle_vline2_pos", 36.0))))
                len2 = max(0.0, min(400.0, float(s.get("reticle_vline2_len", 22.0))))
                pos3 = max(0.0, min(600.0, float(s.get("reticle_vline3_pos", 54.0))))
                len3 = max(0.0, min(400.0, float(s.get("reticle_vline3_len", 28.0))))
                for xpos, vlen in ((pos1, len1), (pos2, len2), (pos3, len3)):
                    vx = hx1 + xpos
                    if vx < 0 or vx > w_q:
                        continue
                    vy1 = hy - (vlen * 0.5)
                    vy2 = hy + (vlen * 0.5)
                    v1x, v1y = _rot(vx, vy1)
                    v2x, v2y = _rot(vx, vy2)
                    p.drawLine(int(v1x), int(v1y), int(v2x), int(v2y))

        pen = QPen(QColor("#ff3333"))
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        r = 4  # small red circle
        p.drawEllipse(int(cx - r), int(cy - r), int(2 * r), int(2 * r))

    def begin(self) -> None:
        self._aim_y = None
        self._last_mouse_y = None
        self._raw_dy_accum = 0.0
        self._active_branch = "top"
        self._was_in_top_trigger = False
        self._was_in_bottom_trigger = False
        ms = max(16, min(200, int(self.settings().get("poll_ms", 33))))
        self._timer.start(ms)
        self.show()
        self.raise_()

    def end(self) -> None:
        self._timer.stop()
        self._unregister_raw_mouse()
        self.hide()
        self._aim_y = None
        self._last_mouse_y = None
        self._raw_dy_accum = 0.0


class QtCrosshairOverlay:
    def __init__(
        self,
        tk_root: tk.Misc,
        get_client_rect: ClientRectFn,
        get_game_hwnd: GameHwndFn,
        settings: Dict[str, Any],
        log: LogFn,
    ) -> None:
        _ensure_qapp()
        self._tk_root = tk_root
        self.settings: Dict[str, Any] = dict(settings)
        self._log = log
        self._surface = _CrosshairSurface(get_client_rect, get_game_hwnd, lambda: self.settings, log)
        self._pumping = False
        self._pump_id: Optional[str] = None

    @property
    def active(self) -> bool:
        return self._surface.isVisible()

    def apply_settings(self, settings: Dict[str, Any]) -> None:
        self.settings = dict(settings)
        self._surface.update()

    def reset_vertical_to_anchor(self) -> None:
        self._surface.reset_vertical_to_anchor()

    def set_vertical_ratio(self, ratio: float) -> bool:
        if not self._surface.isVisible():
            return False
        return self._surface.set_vertical_ratio(ratio)

    def get_vertical_aim_snapshot(self) -> Optional[Dict[str, Any]]:
        if not self._surface.isVisible():
            return None
        return self._surface.get_vertical_aim_snapshot()

    def raw_input_vertical_ready(self) -> bool:
        return bool(getattr(self._surface, "_raw_input_registered", False))

    def _pump_qt(self) -> None:
        _ensure_qapp().processEvents()
        if self._pumping:
            self._pump_id = self._tk_root.after(8, self._pump_qt)

    def _start_pump(self) -> None:
        self._pumping = True
        self._pump_qt()

    def _stop_pump(self) -> None:
        self._pumping = False
        if self._pump_id is not None:
            try:
                self._tk_root.after_cancel(self._pump_id)
            except tk.TclError:
                pass
            self._pump_id = None

    def start(self) -> bool:
        if self._surface.isVisible():
            return True
        self._surface.begin()
        self._start_pump()
        self._log("Qt overlay started.")
        return True

    def stop(self) -> None:
        self._stop_pump()
        self._surface.end()
        self._log("Overlay stopped.")

    def runtime_refresh(self) -> None:
        self._surface.update()
