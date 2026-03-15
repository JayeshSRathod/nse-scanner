"""
nse_progress_window.py — NSE Scanner Progress Window
=====================================================
Launches a GUI progress window while nse_daily_runner.py runs.
Shows live step progress, % bar, elapsed time, status per step.

Usage (called from run_daily_scanner.bat automatically):
    python nse_progress_window.py
    python nse_progress_window.py --dry-run
    python nse_progress_window.py --skip-news
    python nse_progress_window.py --skip-download
"""

import tkinter as tk
from tkinter import ttk, font
import threading
import subprocess
import sys
import os
import time
import argparse
from datetime import datetime, date
from pathlib import Path

# ── Config ────────────────────────────────────────────────────
_HERE      = Path(__file__).parent
VENV_PY    = _HERE / "venv" / "Scripts" / "python.exe"
RUNNER     = _HERE / "nse_daily_runner.py"

# Use venv python if available, else system python
PYTHON_EXE = str(VENV_PY) if VENV_PY.exists() else sys.executable

# Pipeline steps — label, weight (used for % calculation)
STEPS = [
    (0, "Auto-cleanup old data",        5),
    (1, "Download NSE files",           25),
    (2, "Load into database",           10),
    (3, "Scan stocks",                  25),
    (4, "Collect news",                 20),
    (5, "Enrich with news flags",       5),
    (6, "Excel + Telegram",             10),
]
TOTAL_WEIGHT = sum(w for _, _, w in STEPS)

# ── Colours ───────────────────────────────────────────────────
BG          = "#0d1117"    # dark background
BG2         = "#161b22"    # card background
ACCENT      = "#238636"    # green
ACCENT2     = "#1f6feb"    # blue
YELLOW      = "#e3b341"    # warning / running
RED         = "#da3633"    # error
TEXT        = "#c9d1d9"    # main text
TEXT_DIM    = "#8b949e"    # dimmed text
WHITE       = "#ffffff"
BAR_BG      = "#21262d"    # progress bar background


class ScannerProgressWindow:

    def __init__(self, root: tk.Tk, args):
        self.root       = root
        self.args       = args
        self.start_time = time.time()
        self.done       = False
        self.success    = False

        # Step state: {step_num: 'pending'|'running'|'done'|'fail'|'skip'}
        self.step_state = {s[0]: 'pending' for s in STEPS}
        self.step_times = {}   # step_num → elapsed seconds

        self._build_ui()
        self._start_runner()

    # ══════════════════════════════════════════════════════════
    # UI BUILD
    # ══════════════════════════════════════════════════════════

    def _build_ui(self):
        r = self.root
        r.title("NSE Momentum Scanner")
        r.configure(bg=BG)
        r.resizable(False, False)
        r.geometry("560x640")
        r.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── Fonts ─────────────────────────────────────────────
        self.f_title   = tk.font.Font(family="Segoe UI", size=15, weight="bold")
        self.f_sub     = tk.font.Font(family="Segoe UI", size=9)
        self.f_step    = tk.font.Font(family="Segoe UI", size=10)
        self.f_pct     = tk.font.Font(family="Segoe UI", size=28, weight="bold")
        self.f_elapsed = tk.font.Font(family="Segoe UI", size=9)
        self.f_mono    = tk.font.Font(family="Consolas",  size=9)

        # ── Header ────────────────────────────────────────────
        hdr = tk.Frame(r, bg=ACCENT2, pady=16)
        hdr.pack(fill="x")

        tk.Label(hdr, text="NSE MOMENTUM SCANNER",
                 font=self.f_title, bg=ACCENT2, fg=WHITE).pack()
        tk.Label(hdr, text=f"Daily Scan — {date.today().strftime('%d %b %Y')}",
                 font=self.f_sub, bg=ACCENT2, fg="#a8d8f0").pack()

        # ── Big % display ─────────────────────────────────────
        pct_frame = tk.Frame(r, bg=BG, pady=10)
        pct_frame.pack(fill="x")

        self.lbl_pct = tk.Label(pct_frame, text="0%",
                                font=self.f_pct, bg=BG, fg=ACCENT)
        self.lbl_pct.pack()

        self.lbl_status = tk.Label(pct_frame,
                                   text="Initialising...",
                                   font=self.f_sub, bg=BG, fg=TEXT_DIM)
        self.lbl_status.pack()

        # ── Progress bar ──────────────────────────────────────
        bar_frame = tk.Frame(r, bg=BG, padx=24, pady=4)
        bar_frame.pack(fill="x")

        style = ttk.Style()
        style.theme_use("default")
        style.configure("NSE.Horizontal.TProgressbar",
                        troughcolor=BAR_BG,
                        background=ACCENT,
                        borderwidth=0,
                        thickness=18)

        self.progress = ttk.Progressbar(bar_frame,
                                        style="NSE.Horizontal.TProgressbar",
                                        orient="horizontal",
                                        length=512,
                                        mode="determinate",
                                        maximum=100)
        self.progress.pack(fill="x")

        # ── Time row ──────────────────────────────────────────
        time_frame = tk.Frame(r, bg=BG, padx=24, pady=2)
        time_frame.pack(fill="x")

        self.lbl_elapsed = tk.Label(time_frame, text="Elapsed: 00:00",
                                    font=self.f_elapsed, bg=BG, fg=TEXT_DIM)
        self.lbl_elapsed.pack(side="left")

        self.lbl_started = tk.Label(time_frame,
                                    text=f"Started: {datetime.now().strftime('%H:%M:%S')}",
                                    font=self.f_elapsed, bg=BG, fg=TEXT_DIM)
        self.lbl_started.pack(side="right")

        # ── Divider ───────────────────────────────────────────
        tk.Frame(r, bg=BG2, height=1).pack(fill="x", padx=24, pady=6)

        # ── Steps list ────────────────────────────────────────
        steps_outer = tk.Frame(r, bg=BG, padx=24)
        steps_outer.pack(fill="x")

        tk.Label(steps_outer, text="PIPELINE STEPS",
                 font=self.f_elapsed, bg=BG, fg=TEXT_DIM).pack(anchor="w", pady=(0, 4))

        self.step_frames = {}
        for num, label, _ in STEPS:
            row = tk.Frame(steps_outer, bg=BG2, pady=7, padx=12)
            row.pack(fill="x", pady=2)

            # Status icon
            icon = tk.Label(row, text="  ○", width=3,
                            font=self.f_step, bg=BG2, fg=TEXT_DIM)
            icon.pack(side="left")

            # Step label
            lbl = tk.Label(row,
                           text=f"Step {num}  —  {label}",
                           font=self.f_step, bg=BG2, fg=TEXT_DIM,
                           anchor="w")
            lbl.pack(side="left", fill="x", expand=True)

            # Time badge
            time_lbl = tk.Label(row, text="",
                                 font=self.f_elapsed, bg=BG2, fg=TEXT_DIM)
            time_lbl.pack(side="right")

            self.step_frames[num] = (row, icon, lbl, time_lbl)

        # ── Divider ───────────────────────────────────────────
        tk.Frame(r, bg=BG2, height=1).pack(fill="x", padx=24, pady=6)

        # ── Log tail ──────────────────────────────────────────
        log_outer = tk.Frame(r, bg=BG, padx=24)
        log_outer.pack(fill="both", expand=True)

        tk.Label(log_outer, text="LIVE OUTPUT",
                 font=self.f_elapsed, bg=BG, fg=TEXT_DIM).pack(anchor="w")

        self.log_text = tk.Text(log_outer, height=6,
                                bg=BG2, fg=TEXT_DIM,
                                font=self.f_mono,
                                relief="flat",
                                state="disabled",
                                wrap="word",
                                padx=8, pady=6)
        self.log_text.pack(fill="both", expand=True, pady=(2, 12))

        # Start elapsed timer
        self._tick()

    # ══════════════════════════════════════════════════════════
    # STEP STATE UPDATES
    # ══════════════════════════════════════════════════════════

    def _set_step(self, num: int, state: str, elapsed: float = None):
        """Update a step's visual state. Called from background thread via after()."""
        if num not in self.step_frames:
            return

        row, icon, lbl, time_lbl = self.step_frames[num]
        _, label, _ = STEPS[num]

        icons  = {'pending': ('○',  TEXT_DIM),
                  'running': ('▶',  YELLOW),
                  'done':    ('✓',  ACCENT),
                  'fail':    ('✗',  RED),
                  'skip':    ('—',  TEXT_DIM)}
        colors = {'pending': TEXT_DIM,
                  'running': WHITE,
                  'done':    TEXT,
                  'fail':    RED,
                  'skip':    TEXT_DIM}

        ic, ic_color = icons.get(state, ('○', TEXT_DIM))
        tx_color     = colors.get(state, TEXT_DIM)

        icon.config(text=f"  {ic}", fg=ic_color)
        lbl.config(fg=tx_color)

        if elapsed is not None:
            time_lbl.config(text=f"{elapsed:.1f}s", fg=TEXT_DIM)

        # Highlight running row
        bg = "#1c2128" if state == 'running' else BG2
        row.config(bg=bg)
        for w in (icon, lbl, time_lbl):
            w.config(bg=bg)

        self.step_state[num] = state

    def _update_progress(self):
        """Recalculate % from completed step weights."""
        done_weight = sum(
            w for num, _, w in STEPS
            if self.step_state.get(num) in ('done', 'skip', 'fail')
        )
        pct = int((done_weight / TOTAL_WEIGHT) * 100)
        self.progress['value'] = pct
        self.lbl_pct.config(text=f"{pct}%")
        return pct

    def _log(self, line: str):
        """Append a line to the live log box."""
        self.log_text.config(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _tick(self):
        """Update elapsed time every second."""
        if not self.done:
            elapsed = int(time.time() - self.start_time)
            m, s    = divmod(elapsed, 60)
            self.lbl_elapsed.config(text=f"Elapsed: {m:02d}:{s:02d}")
            self.root.after(1000, self._tick)

    # ══════════════════════════════════════════════════════════
    # RUNNER THREAD
    # ══════════════════════════════════════════════════════════

    def _start_runner(self):
        """Launch nse_daily_runner.py in a background thread."""
        t = threading.Thread(target=self._run_pipeline, daemon=True)
        t.start()

    def _run_pipeline(self):
        """
        Run nse_daily_runner.py as subprocess.
        Parse its stdout to update step states in real time.
        """
        cmd = [PYTHON_EXE, str(RUNNER)]
        if hasattr(self.args, 'dry_run')    and self.args.dry_run:
            cmd.append("--dry-run")
        if hasattr(self.args, 'skip_news')  and self.args.skip_news:
            cmd.append("--skip-news")
        if hasattr(self.args, 'skip_download') and self.args.skip_download:
            cmd.append("--skip-download")

        env         = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8']       = '1'

        self.root.after(0, lambda: self.lbl_status.config(
            text="Launching pipeline...", fg=YELLOW))

        current_step     = None
        current_step_t   = None

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                env=env,
                cwd=str(_HERE),
            )

            for raw_line in proc.stdout:
                line = raw_line.rstrip()
                if not line:
                    continue

                # ── Detect step start ──────────────────────
                if "Step " in line and ":" in line and "=" not in line:
                    for num, label, _ in STEPS:
                        marker = f"Step {num}:"
                        if marker in line:
                            # Mark previous step done
                            if current_step is not None:
                                elapsed = time.time() - current_step_t
                                _n, _l  = current_step, elapsed
                                self.root.after(0, lambda n=_n, e=_l:
                                    self._set_step(n, 'done', e))
                                self.root.after(0, self._update_progress)

                            current_step   = num
                            current_step_t = time.time()

                            self.root.after(0, lambda n=num, l=label:
                                self._set_step(n, 'running'))
                            self.root.after(0, lambda l=label:
                                self.lbl_status.config(
                                    text=f"Running: {l}",
                                    fg=YELLOW))
                            break

                # ── Detect step skip ───────────────────────
                if "SKIPPED" in line.upper():
                    for num, label, _ in STEPS:
                        if f"Step {num}" in line:
                            self.root.after(0, lambda n=num:
                                self._set_step(n, 'skip', 0))
                            self.root.after(0, self._update_progress)
                            break

                # ── Detect step fail ───────────────────────
                if "FAILED" in line and current_step is not None:
                    _n = current_step
                    self.root.after(0, lambda n=_n:
                        self._set_step(n, 'fail'))

                # ── Send interesting lines to log box ──────
                keywords = ["Step", "Scan", "Total", "HC", "WL",
                            "Excel", "Telegram", "ERROR", "FAIL",
                            "OK", "Done", "Loaded", "Downloaded",
                            "stocks", "sent", "saved"]
                if any(k in line for k in keywords):
                    self.root.after(0, lambda l=line: self._log(l))

            proc.wait()
            self.success = (proc.returncode == 0)

        except Exception as e:
            self.root.after(0, lambda: self._log(f"ERROR: {e}"))
            self.success = False

        # ── Mark last step done ────────────────────────────
        if current_step is not None:
            elapsed = time.time() - (current_step_t or time.time())
            self.root.after(0, lambda n=current_step, e=elapsed:
                self._set_step(n, 'done' if self.success else 'fail', e))

        self.root.after(0, self._on_pipeline_done)

    # ══════════════════════════════════════════════════════════
    # COMPLETION
    # ══════════════════════════════════════════════════════════

    def _on_pipeline_done(self):
        self.done = True

        total_elapsed = int(time.time() - self.start_time)
        m, s          = divmod(total_elapsed, 60)

        if self.success:
            self.progress['value'] = 100
            self.lbl_pct.config(text="100%", fg=ACCENT)
            self.lbl_status.config(
                text=f"Scan complete!  Total time: {m:02d}:{s:02d}",
                fg=ACCENT)
            # Mark all remaining pending as done
            for num, _, _ in STEPS:
                if self.step_state.get(num) == 'pending':
                    self._set_step(num, 'skip', 0)
                elif self.step_state.get(num) == 'running':
                    self._set_step(num, 'done', 0)

            # Change header to green
            self._log(f"Pipeline complete in {m:02d}:{s:02d}")
            self._log("Check Telegram for your scan results!")

            # Auto-close after 30 seconds
            self.lbl_status.config(
                text=f"Complete! ({m:02d}:{s:02d})  —  Window closes in 30s",
                fg=ACCENT)
            self.root.after(30000, self.root.destroy)

        else:
            self.lbl_pct.config(fg=RED)
            self.lbl_status.config(
                text=f"Completed with errors — check logs/scheduler.log",
                fg=RED)
            self._log("Check logs/scheduler.log for details")

    def _on_close(self):
        """Allow closing window — pipeline keeps running in background."""
        self.root.destroy()


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",       action="store_true")
    parser.add_argument("--skip-news",     action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    args = parser.parse_args()

    root = tk.Tk()

    # Centre on screen
    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x  = (sw - 560) // 2
    y  = (sh - 640) // 2
    root.geometry(f"560x640+{x}+{y}")

    # Keep on top initially
    root.lift()
    root.attributes("-topmost", True)
    root.after(3000, lambda: root.attributes("-topmost", False))

    app = ScannerProgressWindow(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()