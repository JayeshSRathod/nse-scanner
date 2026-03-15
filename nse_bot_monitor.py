"""
nse_bot_monitor.py — Telegram Bot Monitor Window (v2)
=====================================================
Thread-safe GUI monitor using queue.Queue for all updates.
Background thread → puts events in queue → main thread reads every 100ms → updates UI.

Shows:
  - Total users ever connected
  - Active users today
  - Messages today
  - Bot uptime
  - Connected users list with last seen
  - Live activity log (who sent what, when)
  - Raw bot console output

All activity saved to: logs/bot_activity.log
User registry saved to: logs/bot_users.json
"""

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
import threading
import subprocess
import queue
import sys
import os
import re
import json
import time
from datetime import datetime, date
from pathlib import Path

_HERE   = Path(__file__).parent
VENV_PY = _HERE / "venv" / "Scripts" / "python.exe"
BOT_PY  = _HERE / "nse_telegram_polling.py"
LOG_DIR = _HERE / "logs"
LOG_DIR.mkdir(exist_ok=True)

PYTHON_EXE   = str(VENV_PY) if VENV_PY.exists() else sys.executable
ACTIVITY_LOG = LOG_DIR / "bot_activity.log"
USER_DB      = LOG_DIR / "bot_users.json"

# ── Colours ───────────────────────────────────────────────────
BG     = "#0d1117"
BG2    = "#161b22"
BG3    = "#21262d"
GREEN  = "#238636"
BLUE   = "#1f6feb"
YELLOW = "#e3b341"
RED    = "#da3633"
PURPLE = "#8957e5"
TEXT   = "#c9d1d9"
DIM    = "#8b949e"
WHITE  = "#ffffff"


# ── Persistent user registry ──────────────────────────────────

def _load_users() -> dict:
    if USER_DB.exists():
        try:
            return json.loads(USER_DB.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_users(users: dict):
    try:
        USER_DB.write_text(
            json.dumps(users, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception:
        pass


def _log_activity(chat_id: str, name: str, command: str):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | {chat_id} | {name:<20} | {command}\n"
    try:
        with open(ACTIVITY_LOG, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# MONITOR WINDOW
# ══════════════════════════════════════════════════════════════

class BotMonitorWindow:

    def __init__(self, root: tk.Tk):
        self.root       = root
        self.start_time = time.time()
        self.running    = True

        # Thread-safe queue — background thread writes, main thread reads
        self.q = queue.Queue()

        # State
        self.users_all      = _load_users()
        self.users_today    = set()
        self.today_messages = 0
        self.today_str      = date.today().isoformat()

        self._build_ui()

        # Start background bot thread
        threading.Thread(target=self._run_bot, daemon=True).start()

        # Start queue polling — every 100ms
        self._poll_queue()

        # Start uptime ticker — every second
        self._tick_uptime()

    # ══════════════════════════════════════════════════════════
    # UI BUILD
    # ══════════════════════════════════════════════════════════

    def _build_ui(self):
        r = self.root
        r.title("NSE Bot Monitor")
        r.configure(bg=BG)
        r.resizable(True, True)
        r.geometry("700x800")
        r.minsize(600, 600)
        r.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── Fonts ─────────────────────────────────────────────
        f_title = tkfont.Font(family="Segoe UI", size=14, weight="bold")
        f_sub   = tkfont.Font(family="Segoe UI", size=9)
        f_hdr   = tkfont.Font(family="Segoe UI", size=9,  weight="bold")
        f_big   = tkfont.Font(family="Segoe UI", size=22, weight="bold")
        f_small = tkfont.Font(family="Segoe UI", size=8)
        self.f_mono = tkfont.Font(family="Consolas", size=9)

        # ── Header ────────────────────────────────────────────
        hdr = tk.Frame(r, bg=BLUE, pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text="NSE BOT MONITOR",
                 font=f_title, bg=BLUE, fg=WHITE).pack()

        status_row = tk.Frame(hdr, bg=BLUE)
        status_row.pack()
        self.dot = tk.Label(status_row, text="●",
                            font=f_sub, bg=BLUE, fg=YELLOW)
        self.dot.pack(side="left")
        self.lbl_status = tk.Label(status_row,
                                   text="  Starting...",
                                   font=f_sub, bg=BLUE, fg="#a8d8f0")
        self.lbl_status.pack(side="left")

        # ── Stat cards ────────────────────────────────────────
        cards_frame = tk.Frame(r, bg=BG, padx=16, pady=10)
        cards_frame.pack(fill="x")
        cards_frame.columnconfigure((0,1,2,3), weight=1, uniform="c")

        card_data = [
            ("total_users",  "TOTAL USERS",    "0",     PURPLE),
            ("active_today", "ACTIVE TODAY",   "0",     GREEN),
            ("msgs_today",   "MESSAGES TODAY", "0",     BLUE),
            ("uptime",       "UPTIME",         "00:00", YELLOW),
        ]
        self.cards = {}
        for col, (key, label, init, color) in enumerate(card_data):
            card = tk.Frame(cards_frame, bg=BG2, padx=8, pady=10)
            card.grid(row=0, column=col, padx=4, sticky="nsew")
            val = tk.Label(card, text=init,
                           font=f_big, bg=BG2, fg=color)
            val.pack()
            tk.Label(card, text=label,
                     font=f_small, bg=BG2, fg=DIM).pack()
            self.cards[key] = val

        # ── Divider ───────────────────────────────────────────
        tk.Frame(r, bg=BG3, height=1).pack(fill="x", padx=16, pady=4)

        # ── Middle: users left | activity right ───────────────
        mid = tk.Frame(r, bg=BG)
        mid.pack(fill="both", expand=True, padx=16, pady=4)
        mid.columnconfigure(0, weight=2)
        mid.columnconfigure(1, weight=3)
        mid.rowconfigure(0, weight=1)

        # Left — users
        left = tk.Frame(mid, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0,6))
        left.rowconfigure(1, weight=1)

        tk.Label(left, text="CONNECTED USERS",
                 font=f_hdr, bg=BG, fg=DIM).grid(row=0, column=0,
                 sticky="w", pady=(0,4))

        usr_box = tk.Frame(left, bg=BG2)
        usr_box.grid(row=1, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)

        self.user_text = tk.Text(usr_box, bg=BG2, fg=TEXT,
                                 font=self.f_mono, relief="flat",
                                 state="disabled", wrap="none",
                                 padx=6, pady=6)
        sb_u = ttk.Scrollbar(usr_box, orient="vertical",
                             command=self.user_text.yview)
        self.user_text.configure(yscrollcommand=sb_u.set)
        sb_u.pack(side="right", fill="y")
        self.user_text.pack(fill="both", expand=True)

        self.user_text.tag_configure("hdr",      foreground=DIM)
        self.user_text.tag_configure("active",   foreground=GREEN)
        self.user_text.tag_configure("inactive", foreground=DIM)

        # Right — activity
        right = tk.Frame(mid, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        tk.Label(right, text="LIVE ACTIVITY",
                 font=f_hdr, bg=BG, fg=DIM).grid(row=0, column=0,
                 sticky="w", pady=(0,4))

        act_box = tk.Frame(right, bg=BG2)
        act_box.grid(row=1, column=0, sticky="nsew")

        self.act_text = tk.Text(act_box, bg=BG2, fg=TEXT,
                                font=self.f_mono, relief="flat",
                                state="disabled", wrap="none",
                                padx=6, pady=6)
        sb_a = ttk.Scrollbar(act_box, orient="vertical",
                             command=self.act_text.yview)
        self.act_text.configure(yscrollcommand=sb_a.set)
        sb_a.pack(side="right", fill="y")
        self.act_text.pack(fill="both", expand=True)

        self.act_text.tag_configure("ts",   foreground=DIM)
        self.act_text.tag_configure("user", foreground=BLUE)
        self.act_text.tag_configure("btn",  foreground=GREEN)
        self.act_text.tag_configure("msg",  foreground=YELLOW)
        self.act_text.tag_configure("cmd",  foreground=TEXT)

        # ── Console ───────────────────────────────────────────
        tk.Frame(r, bg=BG3, height=1).pack(fill="x", padx=16, pady=4)

        con_outer = tk.Frame(r, bg=BG, padx=16)
        con_outer.pack(fill="x", pady=(0,10))
        tk.Label(con_outer, text="BOT CONSOLE",
                 font=f_hdr, bg=BG, fg=DIM).pack(anchor="w")

        con_box = tk.Frame(con_outer, bg=BG2)
        con_box.pack(fill="x")

        self.console = tk.Text(con_box, height=5, bg=BG2, fg=DIM,
                               font=self.f_mono, relief="flat",
                               state="disabled", wrap="word",
                               padx=6, pady=4)
        self.console.pack(fill="x")

    # ══════════════════════════════════════════════════════════
    # QUEUE POLLING — runs in main thread every 100ms
    # ══════════════════════════════════════════════════════════

    def _poll_queue(self):
        """
        Drain the queue and process all pending events.
        This is the ONLY place UI is updated — always runs in main thread.
        """
        try:
            while True:
                event = self.q.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass

        if self.running:
            self.root.after(100, self._poll_queue)

    def _handle_event(self, event: dict):
        """Process one event from the queue."""
        kind = event.get("kind")

        if kind == "status":
            self.dot.config(fg=event.get("dot_color", YELLOW))
            self.lbl_status.config(text=f"  {event['text']}")

        elif kind == "console":
            self._write_console(event["line"])

        elif kind == "activity":
            self._record_activity(
                event["chat_id"], event["command"], event["source"]
            )

        elif kind == "restart":
            self.dot.config(fg=RED)
            self.lbl_status.config(
                text=f"  Restarting in 10s...")
            self._write_console(event.get("line", "Bot stopped"))

    def _record_activity(self, chat_id: str, command: str, source: str):
        """Update stats + user list + activity log. Runs in main thread."""
        now   = datetime.now()
        today = date.today().isoformat()

        # Reset daily counters at midnight
        if today != self.today_str:
            self.today_str      = today
            self.users_today    = set()
            self.today_messages = 0

        # Update user registry
        if chat_id not in self.users_all:
            self.users_all[chat_id] = {
                "chat_id":    chat_id,
                "name":       f"User_{chat_id[-4:]}",
                "first_seen": now.isoformat(),
                "last_seen":  now.isoformat(),
                "count":      0,
            }

        u              = self.users_all[chat_id]
        u["last_seen"] = now.isoformat()
        u["count"]     = u.get("count", 0) + 1
        _save_users(self.users_all)
        _log_activity(chat_id, u.get("name",""), command)

        # Today tracking
        self.users_today.add(chat_id)
        self.today_messages += 1

        # Update stat cards
        self.cards["total_users"].config(text=str(len(self.users_all)))
        self.cards["active_today"].config(text=str(len(self.users_today)))
        self.cards["msgs_today"].config(text=str(self.today_messages))

        # Rebuild user list
        self._rebuild_user_list()

        # Add activity row
        ts  = now.strftime("%H:%M:%S")
        src = "BTN" if source == "BTN" else "MSG"
        name = u.get("name", f"User_{chat_id[-4:]}")[:12]

        self.act_text.config(state="normal")
        self.act_text.insert("end", f"{ts} ", "ts")
        self.act_text.insert("end", f"{name:<13}", "user")
        self.act_text.insert("end",
            f"[{src}] ", "btn" if src == "BTN" else "msg")
        self.act_text.insert("end", f"{command}\n", "cmd")
        self.act_text.see("end")
        # Keep last 300 lines
        lines = int(self.act_text.index("end").split(".")[0])
        if lines > 300:
            self.act_text.delete("1.0", f"{lines-300}.0")
        self.act_text.config(state="disabled")

    def _rebuild_user_list(self):
        """Rebuild user list panel. Runs in main thread."""
        self.user_text.config(state="normal")
        self.user_text.delete("1.0", "end")

        self.user_text.insert("end",
            f"{'Chat ID':<14} {'Name':<14} {'Msgs':>5} Last\n", "hdr")
        self.user_text.insert("end", "-"*50 + "\n", "hdr")

        # Sort: active today first, then by count desc
        def sort_key(item):
            is_today = item[0] in self.users_today
            return (not is_today, -item[1].get("count", 0))

        for cid, u in sorted(self.users_all.items(), key=sort_key):
            is_today = cid in self.users_today
            tag      = "active" if is_today else "inactive"
            dot      = " ●" if is_today else "  "
            last     = u.get("last_seen","")[:16].replace("T"," ")
            name     = u.get("name", f"User_{cid[-4:]}")[:13]
            count    = u.get("count", 0)
            self.user_text.insert("end",
                f"{cid[-10:]:<14} {name:<14} {count:>5}  {last}{dot}\n",
                tag)

        self.user_text.config(state="disabled")

    def _write_console(self, line: str):
        """Append to console. Runs in main thread."""
        self.console.config(state="normal")
        self.console.insert("end", line + "\n")
        self.console.see("end")
        lines = int(self.console.index("end").split(".")[0])
        if lines > 200:
            self.console.delete("1.0", f"{lines-200}.0")
        self.console.config(state="disabled")

    # ══════════════════════════════════════════════════════════
    # UPTIME TICKER — main thread, every second
    # ══════════════════════════════════════════════════════════

    def _tick_uptime(self):
        if self.running:
            elapsed = int(time.time() - self.start_time)
            h, rem  = divmod(elapsed, 3600)
            m, s    = divmod(rem, 60)
            text    = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
            self.cards["uptime"].config(text=text)
            self.root.after(1000, self._tick_uptime)

    # ══════════════════════════════════════════════════════════
    # BACKGROUND BOT THREAD — only touches queue, never UI
    # ══════════════════════════════════════════════════════════

    def _run_bot(self):
        """
        Run nse_telegram_polling.py as subprocess.
        Parse stdout and put events into self.q.
        NEVER touches tkinter widgets directly.
        """
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8']       = '1'

        self.q.put({"kind": "status",
                    "text": "Starting bot...",
                    "dot_color": YELLOW})

        while self.running:
            try:
                proc = subprocess.Popen(
                    [PYTHON_EXE, str(BOT_PY)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    env=env,
                    cwd=str(_HERE),
                )

                self.q.put({"kind": "status",
                            "text": "Bot: RUNNING @nsescanner_bot",
                            "dot_color": GREEN})

                for raw in proc.stdout:
                    if not self.running:
                        proc.terminate()
                        break

                    line = raw.rstrip()
                    if not line:
                        continue

                    # Always send to console
                    self.q.put({"kind": "console", "line": line})

                    # ── Parse bot confirmed running ──────────
                    if "[OK]" in line and "Bot:" in line:
                        self.q.put({"kind": "status",
                                    "text": line.split("[OK]")[1].strip(),
                                    "dot_color": GREEN})

                    # ── Parse user message ───────────────────
                    # [MSG] chat=7872191203  text='hi'
                    m = re.search(
                        r'\[MSG\]\s+chat=(\d+)\s+text=(.+)', line)
                    if m:
                        self.q.put({
                            "kind":    "activity",
                            "chat_id": m.group(1),
                            "command": m.group(2).strip().strip("'\""),
                            "source":  "MSG",
                        })
                        continue

                    # ── Parse button tap ─────────────────────
                    # [CB]  chat=7872191203  data='next'
                    m2 = re.search(
                        r'\[CB\]\s+chat=(\d+)\s+data=(.+)', line)
                    if m2:
                        self.q.put({
                            "kind":    "activity",
                            "chat_id": m2.group(1),
                            "command": m2.group(2).strip().strip("'\""),
                            "source":  "BTN",
                        })

                proc.wait()

            except Exception as e:
                self.q.put({"kind": "console", "line": f"ERROR: {e}"})

            if self.running:
                self.q.put({"kind": "restart",
                            "line": "Bot stopped — restarting in 10s..."})
                time.sleep(10)
                self.q.put({"kind": "status",
                            "text": "Restarting...",
                            "dot_color": YELLOW})

    # ══════════════════════════════════════════════════════════
    # CLOSE
    # ══════════════════════════════════════════════════════════

    def _on_close(self):
        self.running = False
        self.root.destroy()


# ── Main ──────────────────────────────────────────────────────

def main():
    root = tk.Tk()

    # Centre on screen
    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x  = (sw - 700) // 2
    y  = (sh - 800) // 2
    root.geometry(f"700x800+{x}+{y}")

    root.lift()
    root.attributes("-topmost", True)
    root.after(3000, lambda: root.attributes("-topmost", False))

    BotMonitorWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()