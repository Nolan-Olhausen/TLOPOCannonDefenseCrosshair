"""
Minimal Cannon Defense crosshair control app.

Focuses only on:
- start point + clamp endpoints
- section speed tuning (top/mid/bottom + split boundaries)
"""

from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Dict, Optional, Tuple

from .qt_crosshair_overlay import QtCrosshairOverlay
from .tlopo_game_window import TlopoGameWindow, enable_process_dpi_awareness


def _config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "crosshair_settings.json"


def _default_settings() -> Dict[str, Any]:
    return {
        "vertical_anchor_ratio": 0.15,
        "vertical_aim_min_ratio": 0.13,
        "vertical_aim_max_ratio": 0.34,
        "vertical_sensitivity": 1.0,
        "vertical_raw_scale": 0.32,
        "vertical_baseline_client_height": 1050.0,
        "vertical_aim_input_mode": "screen",
        "vertical_speed_use_sections": True,
        "bottom_branch_section_sens_top": 2.0,
        "bottom_branch_section_sens_mid": 2.0,
        "bottom_branch_section_sens_bottom": 2.0,
        "bottom_branch_section_split1": 0.3333,
        "bottom_branch_section_split2": 0.6667,
        "bottom_branch_trigger_min": 0.3350,
        "bottom_branch_trigger_max": 0.3440,
        "top_branch_section_sens_top": 2.0,
        "top_branch_section_sens_mid": 2.0,
        "top_branch_section_sens_bottom": 2.0,
        "top_branch_section_sens_low": 2.0,
        "top_branch_section_split1": 0.3333,
        "top_branch_section_split2": 0.6667,
        "top_branch_section_split3": 0.8750,
        "top_branch_trigger_min": 0.1325,
        "top_branch_trigger_max": 0.1400,
        "vertical_section_overlay": True,
        "reticle_right_line_enabled": True,
        "reticle_right_line_length": 70.0,
        "reticle_right_line_y_offset": 0.0,
        "reticle_right_line_start_gap": 1.0,
        "reticle_right_line_rotation_deg": 0.0,
        "reticle_vline1_pos": 18.0,
        "reticle_vline1_len": 16.0,
        "reticle_vline2_pos": 36.0,
        "reticle_vline2_len": 22.0,
        "reticle_vline3_pos": 54.0,
        "reticle_vline3_len": 28.0,
        "vertical_arc_enabled": False,
        "poll_ms": 33,
        "title_substrings": [
            "The Legend of Pirates Online [BETA]",
            "The Legend of Pirates Online",
            "TLOPO",
        ],
        "process_names": ["tlopo.exe"],
    }


def load_settings(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or _config_path()
    data = _default_settings()
    if p.is_file():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                # Keep only keys used by the simplified section-speed system.
                for k in data.keys():
                    if k in raw:
                        data[k] = raw[k]
                # Backward-compat: map single-branch settings into both branches.
                if "vertical_section_speed_top" in raw and "bottom_branch_section_sens_top" not in raw:
                    data["bottom_branch_section_sens_top"] = float(raw["vertical_section_speed_top"])
                    data["top_branch_section_sens_top"] = float(raw["vertical_section_speed_top"])
                if "vertical_section_speed_mid" in raw and "bottom_branch_section_sens_mid" not in raw:
                    data["bottom_branch_section_sens_mid"] = float(raw["vertical_section_speed_mid"])
                    data["top_branch_section_sens_mid"] = float(raw["vertical_section_speed_mid"])
                if "vertical_section_speed_bottom" in raw and "bottom_branch_section_sens_bottom" not in raw:
                    data["bottom_branch_section_sens_bottom"] = float(raw["vertical_section_speed_bottom"])
                    data["top_branch_section_sens_bottom"] = float(raw["vertical_section_speed_bottom"])
                    data["top_branch_section_sens_low"] = float(raw["vertical_section_speed_bottom"])
                if "vertical_section_split1" in raw and "bottom_branch_section_split1" not in raw:
                    data["bottom_branch_section_split1"] = float(raw["vertical_section_split1"])
                    data["top_branch_section_split1"] = float(raw["vertical_section_split1"])
                if "vertical_section_split2" in raw and "bottom_branch_section_split2" not in raw:
                    data["bottom_branch_section_split2"] = float(raw["vertical_section_split2"])
                    data["top_branch_section_split2"] = float(raw["vertical_section_split2"])
                    data["top_branch_section_split3"] = (float(raw["vertical_section_split2"]) + 1.0) * 0.5
        except Exception:
            pass
    return data


def save_settings(data: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = path or _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)


class CrosshairControlApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Cannon Defense crosshair (section speed only)")
        self.root.geometry("820x620")
        self.root.minsize(760, 520)
        self.settings = load_settings()
        self._log_lines: list[str] = []
        self._all_logs: list[str] = []

        titles = self.settings.get("title_substrings")
        procs = self.settings.get("process_names")
        if not isinstance(titles, list):
            titles = list(_default_settings()["title_substrings"])
        if not isinstance(procs, list):
            procs = list(_default_settings()["process_names"])

        self.game = TlopoGameWindow(
            proc_names=tuple(str(x) for x in procs),
            title_keywords=tuple(str(x) for x in titles),
            log=self._log,
        )
        self.overlay: Optional[QtCrosshairOverlay] = None
        self._build_ui()
        self.overlay = QtCrosshairOverlay(
            self.root,
            get_client_rect=self._client_rect,
            get_game_hwnd=self.game.get_hwnd,
            settings=self.settings,
            log=self._log,
        )

    def _log(self, msg: str) -> None:
        self._all_logs.append(msg)
        self._log_lines.append(msg)
        self._log_lines = self._log_lines[-4:]
        if hasattr(self, "status_var"):
            self.status_var.set("\n".join(self._log_lines))

    def _show_logs_popup(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Cannon Defense Logs")
        win.geometry("980x520")
        win.minsize(760, 360)

        txt = tk.Text(win, wrap="none")
        yscroll = ttk.Scrollbar(win, orient="vertical", command=txt.yview)
        xscroll = ttk.Scrollbar(win, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        txt.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)

        txt.insert("1.0", "\n".join(self._all_logs))
        txt.configure(state="disabled")

        bf = ttk.Frame(win, padding=6)
        bf.grid(row=2, column=0, columnspan=2, sticky="w")

        def _refresh() -> None:
            txt.configure(state="normal")
            txt.delete("1.0", tk.END)
            txt.insert("1.0", "\n".join(self._all_logs))
            txt.see(tk.END)
            txt.configure(state="disabled")

        def _copy_all() -> None:
            win.clipboard_clear()
            win.clipboard_append("\n".join(self._all_logs))

        ttk.Button(bf, text="Refresh", command=_refresh).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bf, text="Copy all", command=_copy_all).pack(side=tk.LEFT)

    def _client_rect(self) -> Optional[Tuple[int, int, int, int]]:
        return self.game.get_client_rect_mss_aligned() or self.game.get_client_rect()

    def _build_ui(self) -> None:
        pad = {"padx": 6, "pady": 4}
        outer = ttk.Frame(self.root, padding=0)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        canvas = tk.Canvas(outer, highlightthickness=0)
        vscroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")

        frm = ttk.Frame(canvas, padding=10)
        win_id = canvas.create_window((0, 0), window=frm, anchor="nw")

        def _sync_scroll_region(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_inner_width(event) -> None:
            canvas.itemconfigure(win_id, width=event.width)

        frm.bind("<Configure>", _sync_scroll_region)
        canvas.bind("<Configure>", _sync_inner_width)

        def _on_mousewheel(event) -> None:
            # Windows mouse wheel delta is typically +/-120 per notch.
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        row = 0
        ttk.Button(frm, text="Find game window", command=self._on_find).grid(row=row, column=0, **pad)
        ttk.Button(frm, text="Start overlay", command=self._on_start).grid(row=row, column=1, **pad)
        ttk.Button(frm, text="Stop overlay", command=self._on_stop).grid(row=row, column=2, **pad)
        ttk.Button(frm, text="View full logs", command=self._show_logs_popup).grid(row=row, column=3, **pad)
        row += 1

        self.status_var = tk.StringVar(value="Find game, start overlay, then tune sections.")
        ttk.Label(frm, textvariable=self.status_var, wraplength=620, justify=tk.LEFT).grid(
            row=row, column=0, columnspan=3, sticky="w", **pad
        )
        row += 1

        ttk.Separator(frm, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", **pad)
        row += 1

        ttk.Label(frm, text="Starting point (vertical_anchor_ratio)").grid(row=row, column=0, sticky="w", **pad)
        self.anchor_ratio_var = tk.DoubleVar(value=float(self.settings.get("vertical_anchor_ratio", 0.15)))
        tk.Spinbox(frm, from_=0.0, to=1.0, increment=0.0001, format="%.4f", textvariable=self.anchor_ratio_var, width=10).grid(
            row=row, column=1, sticky="w", **pad
        )
        row += 1

        ttk.Label(frm, text="Clamp endpoint min ratio").grid(row=row, column=0, sticky="w", **pad)
        clamp_f = ttk.Frame(frm)
        clamp_f.grid(row=row, column=1, sticky="w", **pad)
        self.aim_min_ratio_var = tk.DoubleVar(value=float(self.settings.get("vertical_aim_min_ratio", 0.13)))
        self.aim_max_ratio_var = tk.DoubleVar(value=float(self.settings.get("vertical_aim_max_ratio", 0.34)))
        tk.Spinbox(clamp_f, from_=0.0, to=1.0, increment=0.0001, format="%.4f", textvariable=self.aim_min_ratio_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Clamp endpoint max ratio").grid(row=row, column=0, sticky="w", **pad)
        clamp2_f = ttk.Frame(frm)
        clamp2_f.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(clamp2_f, from_=0.0, to=1.0, increment=0.0001, format="%.4f", textvariable=self.aim_max_ratio_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="vertical_raw_scale").grid(row=row, column=0, sticky="w", **pad)
        self.raw_scale_var = tk.DoubleVar(value=float(self.settings.get("vertical_raw_scale", 0.32)))
        tk.Spinbox(frm, from_=0.05, to=2.0, increment=0.0001, format="%.4f", textvariable=self.raw_scale_var, width=10).grid(
            row=row, column=1, sticky="w", **pad
        )
        row += 1

        ttk.Label(frm, text="Baseline client height (for normalization)").grid(row=row, column=0, sticky="w", **pad)
        self.base_client_h_var = tk.DoubleVar(value=float(self.settings.get("vertical_baseline_client_height", 1050.0)))
        tk.Spinbox(frm, from_=100.0, to=4000.0, increment=1.0, format="%.4f", textvariable=self.base_client_h_var, width=10).grid(
            row=row, column=1, sticky="w", **pad
        )
        row += 1

        ttk.Separator(frm, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", **pad)
        row += 1

        ttk.Label(frm, text="Bottom Start branch (current working branch)").grid(
            row=row, column=0, columnspan=3, sticky="w", **pad
        )
        row += 1
        ttk.Label(frm, text="Bottom branch sensitivity (top)").grid(row=row, column=0, sticky="w", **pad)
        sec_f = ttk.Frame(frm)
        sec_f.grid(row=row, column=1, sticky="w", **pad)
        self.bot_top_var = tk.DoubleVar(value=float(self.settings.get("bottom_branch_section_sens_top", 2.0)))
        self.bot_mid_var = tk.DoubleVar(value=float(self.settings.get("bottom_branch_section_sens_mid", 2.0)))
        self.bot_bot_var = tk.DoubleVar(value=float(self.settings.get("bottom_branch_section_sens_bottom", 2.0)))
        self.top_top_var = tk.DoubleVar(value=float(self.settings.get("top_branch_section_sens_top", float(self.bot_top_var.get()))))
        self.top_mid_var = tk.DoubleVar(value=float(self.settings.get("top_branch_section_sens_mid", float(self.bot_mid_var.get()))))
        self.top_bot_var = tk.DoubleVar(value=float(self.settings.get("top_branch_section_sens_bottom", float(self.bot_bot_var.get()))))
        self.top_low_var = tk.DoubleVar(value=float(self.settings.get("top_branch_section_sens_low", float(self.top_bot_var.get()))))
        self.bot_split1_var = tk.DoubleVar(value=float(self.settings.get("bottom_branch_section_split1", 0.3333)))
        self.bot_split2_var = tk.DoubleVar(value=float(self.settings.get("bottom_branch_section_split2", 0.6667)))
        self.top_split1_var = tk.DoubleVar(value=float(self.settings.get("top_branch_section_split1", float(self.bot_split1_var.get()))))
        self.top_split2_var = tk.DoubleVar(value=float(self.settings.get("top_branch_section_split2", float(self.bot_split2_var.get()))))
        self.top_split3_var = tk.DoubleVar(value=float(self.settings.get("top_branch_section_split3", 0.8750)))
        self.bot_trigger_min_var = tk.DoubleVar(value=float(self.settings.get("bottom_branch_trigger_min", 0.3350)))
        self.bot_trigger_max_var = tk.DoubleVar(value=float(self.settings.get("bottom_branch_trigger_max", 0.3440)))
        self.top_trigger_min_var = tk.DoubleVar(value=float(self.settings.get("top_branch_trigger_min", 0.1325)))
        self.top_trigger_max_var = tk.DoubleVar(value=float(self.settings.get("top_branch_trigger_max", 0.1400)))
        self.reticle_right_line_enabled_var = tk.BooleanVar(value=bool(self.settings.get("reticle_right_line_enabled", True)))
        self.reticle_right_line_length_var = tk.DoubleVar(value=float(self.settings.get("reticle_right_line_length", 70.0)))
        self.reticle_right_line_y_offset_var = tk.DoubleVar(value=float(self.settings.get("reticle_right_line_y_offset", 0.0)))
        self.reticle_right_line_start_gap_var = tk.DoubleVar(value=float(self.settings.get("reticle_right_line_start_gap", 1.0)))
        self.reticle_right_line_rotation_deg_var = tk.DoubleVar(value=float(self.settings.get("reticle_right_line_rotation_deg", 0.0)))
        self.reticle_vline1_pos_var = tk.DoubleVar(value=float(self.settings.get("reticle_vline1_pos", 18.0)))
        self.reticle_vline1_len_var = tk.DoubleVar(value=float(self.settings.get("reticle_vline1_len", 16.0)))
        self.reticle_vline2_pos_var = tk.DoubleVar(value=float(self.settings.get("reticle_vline2_pos", 36.0)))
        self.reticle_vline2_len_var = tk.DoubleVar(value=float(self.settings.get("reticle_vline2_len", 22.0)))
        self.reticle_vline3_pos_var = tk.DoubleVar(value=float(self.settings.get("reticle_vline3_pos", 54.0)))
        self.reticle_vline3_len_var = tk.DoubleVar(value=float(self.settings.get("reticle_vline3_len", 28.0)))
        tk.Spinbox(sec_f, from_=0.05, to=4.0, increment=0.0001, format="%.4f", textvariable=self.bot_top_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Bottom branch sensitivity (middle)").grid(row=row, column=0, sticky="w", **pad)
        sec_m_f = ttk.Frame(frm)
        sec_m_f.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(sec_m_f, from_=0.05, to=4.0, increment=0.0001, format="%.4f", textvariable=self.bot_mid_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Bottom branch sensitivity (bottom)").grid(row=row, column=0, sticky="w", **pad)
        sec_b_f = ttk.Frame(frm)
        sec_b_f.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(sec_b_f, from_=0.05, to=4.0, increment=0.0001, format="%.4f", textvariable=self.bot_bot_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Bottom branch split (top|middle)").grid(row=row, column=0, sticky="w", **pad)
        split_f = ttk.Frame(frm)
        split_f.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(split_f, from_=0.0, to=1.0, increment=0.0001, format="%.4f", textvariable=self.bot_split1_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Bottom branch split (middle|bottom)").grid(row=row, column=0, sticky="w", **pad)
        split2_f = ttk.Frame(frm)
        split2_f.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(split2_f, from_=0.0, to=1.0, increment=0.0001, format="%.4f", textvariable=self.bot_split2_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Bottom branch trigger min").grid(row=row, column=0, sticky="w", **pad)
        btr1 = ttk.Frame(frm)
        btr1.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(btr1, from_=0.0, to=1.0, increment=0.0001, format="%.4f", textvariable=self.bot_trigger_min_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Bottom branch trigger max").grid(row=row, column=0, sticky="w", **pad)
        btr2 = ttk.Frame(frm)
        btr2.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(btr2, from_=0.0, to=1.0, increment=0.0001, format="%.4f", textvariable=self.bot_trigger_max_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Separator(frm, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", **pad)
        row += 1
        ttk.Label(frm, text="Top Start branch (starter duplicate)").grid(
            row=row, column=0, columnspan=3, sticky="w", **pad
        )
        row += 1

        ttk.Label(frm, text="Top branch sensitivity (top)").grid(row=row, column=0, sticky="w", **pad)
        ts1 = ttk.Frame(frm)
        ts1.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(ts1, from_=0.05, to=4.0, increment=0.0001, format="%.4f", textvariable=self.top_top_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Top branch sensitivity (middle)").grid(row=row, column=0, sticky="w", **pad)
        ts2 = ttk.Frame(frm)
        ts2.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(ts2, from_=0.05, to=4.0, increment=0.0001, format="%.4f", textvariable=self.top_mid_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Top branch sensitivity (bottom)").grid(row=row, column=0, sticky="w", **pad)
        ts3 = ttk.Frame(frm)
        ts3.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(ts3, from_=0.05, to=4.0, increment=0.0001, format="%.4f", textvariable=self.top_bot_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Top branch sensitivity (4th/lower bottom)").grid(row=row, column=0, sticky="w", **pad)
        ts4 = ttk.Frame(frm)
        ts4.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(ts4, from_=0.05, to=4.0, increment=0.0001, format="%.4f", textvariable=self.top_low_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Top branch split (top|middle)").grid(row=row, column=0, sticky="w", **pad)
        tsp1 = ttk.Frame(frm)
        tsp1.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(tsp1, from_=0.0, to=1.0, increment=0.0001, format="%.4f", textvariable=self.top_split1_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Top branch split (middle|bottom)").grid(row=row, column=0, sticky="w", **pad)
        tsp2 = ttk.Frame(frm)
        tsp2.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(tsp2, from_=0.0, to=1.0, increment=0.0001, format="%.4f", textvariable=self.top_split2_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Top branch split (bottom|4th lower)").grid(row=row, column=0, sticky="w", **pad)
        tsp3 = ttk.Frame(frm)
        tsp3.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(tsp3, from_=0.0, to=1.0, increment=0.0001, format="%.4f", textvariable=self.top_split3_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Top branch trigger min").grid(row=row, column=0, sticky="w", **pad)
        ttr1 = ttk.Frame(frm)
        ttr1.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(ttr1, from_=0.0, to=1.0, increment=0.0001, format="%.4f", textvariable=self.top_trigger_min_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Top branch trigger max").grid(row=row, column=0, sticky="w", **pad)
        ttr2 = ttk.Frame(frm)
        ttr2.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(ttr2, from_=0.0, to=1.0, increment=0.0001, format="%.4f", textvariable=self.top_trigger_max_var, width=8).pack(side=tk.LEFT)
        row += 1

        self.section_overlay_var = tk.BooleanVar(value=bool(self.settings.get("vertical_section_overlay", True)))
        ttk.Checkbutton(frm, text="Show section rectangles on overlay", variable=self.section_overlay_var).grid(
            row=row, column=0, columnspan=3, sticky="w", **pad
        )
        row += 1

        ttk.Separator(frm, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", **pad)
        row += 1
        ttk.Checkbutton(
            frm,
            text="Show right-side reticle line attachment",
            variable=self.reticle_right_line_enabled_var,
        ).grid(row=row, column=0, columnspan=3, sticky="w", **pad)
        row += 1

        ttk.Label(frm, text="Right line length (px)").grid(row=row, column=0, sticky="w", **pad)
        rl1 = ttk.Frame(frm)
        rl1.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(rl1, from_=0.0, to=600.0, increment=0.1, format="%.4f", textvariable=self.reticle_right_line_length_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Right line Y offset from center (px)").grid(row=row, column=0, sticky="w", **pad)
        rl2 = ttk.Frame(frm)
        rl2.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(rl2, from_=-400.0, to=400.0, increment=0.1, format="%.4f", textvariable=self.reticle_right_line_y_offset_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Right line start gap from circle (px)").grid(row=row, column=0, sticky="w", **pad)
        rl3 = ttk.Frame(frm)
        rl3.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(rl3, from_=0.0, to=80.0, increment=0.1, format="%.4f", textvariable=self.reticle_right_line_start_gap_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Right line rotation around circle (deg)").grid(row=row, column=0, sticky="w", **pad)
        rl4 = ttk.Frame(frm)
        rl4.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(rl4, from_=-180.0, to=180.0, increment=0.1, format="%.4f", textvariable=self.reticle_right_line_rotation_deg_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Vertical line 1 position on right line (px)").grid(row=row, column=0, sticky="w", **pad)
        rv1 = ttk.Frame(frm)
        rv1.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(rv1, from_=0.0, to=600.0, increment=0.1, format="%.4f", textvariable=self.reticle_vline1_pos_var, width=8).pack(side=tk.LEFT)
        row += 1
        ttk.Label(frm, text="Vertical line 1 length (px)").grid(row=row, column=0, sticky="w", **pad)
        rv1l = ttk.Frame(frm)
        rv1l.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(rv1l, from_=0.0, to=400.0, increment=0.1, format="%.4f", textvariable=self.reticle_vline1_len_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Vertical line 2 position on right line (px)").grid(row=row, column=0, sticky="w", **pad)
        rv2 = ttk.Frame(frm)
        rv2.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(rv2, from_=0.0, to=600.0, increment=0.1, format="%.4f", textvariable=self.reticle_vline2_pos_var, width=8).pack(side=tk.LEFT)
        row += 1
        ttk.Label(frm, text="Vertical line 2 length (px)").grid(row=row, column=0, sticky="w", **pad)
        rv2l = ttk.Frame(frm)
        rv2l.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(rv2l, from_=0.0, to=400.0, increment=0.1, format="%.4f", textvariable=self.reticle_vline2_len_var, width=8).pack(side=tk.LEFT)
        row += 1

        ttk.Label(frm, text="Vertical line 3 position on right line (px)").grid(row=row, column=0, sticky="w", **pad)
        rv3 = ttk.Frame(frm)
        rv3.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(rv3, from_=0.0, to=600.0, increment=0.1, format="%.4f", textvariable=self.reticle_vline3_pos_var, width=8).pack(side=tk.LEFT)
        row += 1
        ttk.Label(frm, text="Vertical line 3 length (px)").grid(row=row, column=0, sticky="w", **pad)
        rv3l = ttk.Frame(frm)
        rv3l.grid(row=row, column=1, sticky="w", **pad)
        tk.Spinbox(rv3l, from_=0.0, to=400.0, increment=0.1, format="%.4f", textvariable=self.reticle_vline3_len_var, width=8).pack(side=tk.LEFT)
        row += 1

        bf = ttk.Frame(frm)
        bf.grid(row=row, column=0, columnspan=3, **pad)
        ttk.Button(bf, text="Apply to running overlay", command=self._apply_runtime).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bf, text="Reset vertical to anchor", command=self._reset_vertical_anchor).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bf, text="Save settings.json", command=self._save).pack(side=tk.LEFT)

    def _gather(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "vertical_anchor_ratio": float(self.anchor_ratio_var.get()),
            "vertical_aim_min_ratio": float(self.aim_min_ratio_var.get()),
            "vertical_aim_max_ratio": float(self.aim_max_ratio_var.get()),
            "vertical_sensitivity": 1.0,
            "vertical_raw_scale": max(0.02, min(2.0, float(self.raw_scale_var.get()))),
            "vertical_baseline_client_height": max(100.0, min(4000.0, float(self.base_client_h_var.get()))),
            "vertical_aim_input_mode": "screen",
            "vertical_speed_use_sections": True,
            "bottom_branch_section_sens_top": float(self.bot_top_var.get()),
            "bottom_branch_section_sens_mid": float(self.bot_mid_var.get()),
            "bottom_branch_section_sens_bottom": float(self.bot_bot_var.get()),
            "top_branch_section_sens_top": float(self.top_top_var.get()),
            "top_branch_section_sens_mid": float(self.top_mid_var.get()),
            "top_branch_section_sens_bottom": float(self.top_bot_var.get()),
            "top_branch_section_sens_low": float(self.top_low_var.get()),
            "vertical_section_overlay": bool(self.section_overlay_var.get()),
            "reticle_right_line_enabled": bool(self.reticle_right_line_enabled_var.get()),
            "reticle_right_line_length": max(0.0, min(600.0, float(self.reticle_right_line_length_var.get()))),
            "reticle_right_line_y_offset": max(-400.0, min(400.0, float(self.reticle_right_line_y_offset_var.get()))),
            "reticle_right_line_start_gap": max(0.0, min(80.0, float(self.reticle_right_line_start_gap_var.get()))),
            "reticle_right_line_rotation_deg": max(-180.0, min(180.0, float(self.reticle_right_line_rotation_deg_var.get()))),
            "reticle_vline1_pos": max(0.0, min(600.0, float(self.reticle_vline1_pos_var.get()))),
            "reticle_vline1_len": max(0.0, min(400.0, float(self.reticle_vline1_len_var.get()))),
            "reticle_vline2_pos": max(0.0, min(600.0, float(self.reticle_vline2_pos_var.get()))),
            "reticle_vline2_len": max(0.0, min(400.0, float(self.reticle_vline2_len_var.get()))),
            "reticle_vline3_pos": max(0.0, min(600.0, float(self.reticle_vline3_pos_var.get()))),
            "reticle_vline3_len": max(0.0, min(400.0, float(self.reticle_vline3_len_var.get()))),
            "vertical_arc_enabled": False,
            "poll_ms": int(self.settings.get("poll_ms", 33)),
            "title_substrings": list(self.settings.get("title_substrings", _default_settings()["title_substrings"])),
            "process_names": list(self.settings.get("process_names", _default_settings()["process_names"])),
        }
        bs1 = max(0.0, min(1.0, float(self.bot_split1_var.get())))
        bs2 = max(0.0, min(1.0, float(self.bot_split2_var.get())))
        if bs2 < bs1:
            bs1, bs2 = bs2, bs1
        ts1 = max(0.0, min(1.0, float(self.top_split1_var.get())))
        ts2 = max(0.0, min(1.0, float(self.top_split2_var.get())))
        ts3 = max(0.0, min(1.0, float(self.top_split3_var.get())))
        if ts2 < ts1:
            ts1, ts2 = ts2, ts1
        if ts3 < ts2:
            ts3 = ts2
        bt1 = float(self.bot_trigger_min_var.get())
        bt2 = float(self.bot_trigger_max_var.get())
        tt1 = float(self.top_trigger_min_var.get())
        tt2 = float(self.top_trigger_max_var.get())
        d["bottom_branch_section_split1"] = bs1
        d["bottom_branch_section_split2"] = bs2
        d["top_branch_section_split1"] = ts1
        d["top_branch_section_split2"] = ts2
        d["top_branch_section_split3"] = ts3
        d["bottom_branch_trigger_min"] = max(0.0, min(1.0, min(bt1, bt2)))
        d["bottom_branch_trigger_max"] = max(0.0, min(1.0, max(bt1, bt2)))
        d["top_branch_trigger_min"] = max(0.0, min(1.0, min(tt1, tt2)))
        d["top_branch_trigger_max"] = max(0.0, min(1.0, max(tt1, tt2)))
        return d

    def _on_find(self) -> None:
        ok = self.game.find_window()
        if ok:
            title = self.game.get_window_title()
            hwnd = self.game.get_hwnd()
            info = self.game.get_window_info() or {}
            win = info.get("window") if isinstance(info.get("window"), dict) else {}
            client = info.get("client") if isinstance(info.get("client"), dict) else {}
            aligned = self.game.get_client_rect_mss_aligned()
            self._log(f"Found: {title!r} hwnd={hwnd}")
            if win:
                self._log(
                    "Window: "
                    f"title={str(win.get('title', ''))!r} "
                    f"handle={win.get('handle', '')}"
                )
            if client:
                self._log(
                    "Client rect: "
                    f"left={client.get('left')} top={client.get('top')} "
                    f"right={client.get('right')} bottom={client.get('bottom')} "
                    f"w={client.get('width')} h={client.get('height')}"
                )
                self._log(
                    f"Suggested baseline_client_height for normalization: {client.get('height')}"
                )
            if aligned:
                l, t, r, b = aligned
                self._log(
                    f"MSS aligned client rect: left={l} top={t} right={r} bottom={b} "
                    f"w={r-l} h={b-t}"
                )
        else:
            self._log("No TLOPO window matched. Is the game running?")

    def _on_start(self) -> None:
        if not self.game.get_hwnd() or not self.game.is_valid():
            self._on_find()
        if not self.game.get_hwnd():
            self._log("Cannot start: no window.")
            return
        if self.overlay is None:
            return
        self.overlay.apply_settings(self._gather())
        if self.overlay.active:
            self._log("Overlay already running.")
            return
        if self.overlay.start():
            self._log("Overlay started.")
        else:
            self._log("Start failed (client rect?).")

    def _on_stop(self) -> None:
        if self.overlay:
            self.overlay.stop()
        self._log("Overlay stopped.")

    def _reset_vertical_anchor(self) -> None:
        if self.overlay and self.overlay.active:
            self.overlay.apply_settings(self._gather())
            self.overlay.reset_vertical_to_anchor()
            self._log("Vertical reset to anchor.")

    def _apply_runtime(self) -> None:
        self.settings = self._gather()
        if self.overlay and self.overlay.active:
            self.overlay.apply_settings(self.settings)
            self.overlay.runtime_refresh()
        self._log("Applied runtime settings.")

    def _save(self) -> None:
        self.settings = self._gather()
        save_settings(self.settings)
        self._log("Saved crosshair_settings.json")


def main() -> None:
    if sys.platform != "win32":
        print("This overlay targets Windows (Win32 window alignment).")
        sys.exit(1)
    enable_process_dpi_awareness()
    root = tk.Tk()
    root.resizable(True, True)
    app = CrosshairControlApp(root)

    def on_close() -> None:
        if app.overlay:
            app.overlay.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
