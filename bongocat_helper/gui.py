"""Control panel (tkinter). The engine runs in a worker thread; the UI polls a queue.

Setup / bubble setup / debug need OpenCV drag windows and console prompts, so they open
in their own console window running this same program's CLI.
"""
import datetime
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import capture
import chatlog
import config
import debug
import engine as engine_mod
import ocr
import store as store_mod

SIDE_KO = {"left": "왼쪽", "right": "오른쪽"}
RESULT_TAG = {"dry_run": "ok", "clicked_ok": "ok", "skipped": "bad", "unmatched": "muted",
              "cooldown": "muted", "clicked_no_change": "bad", "late": "bad", "chat": "chat",
              "clicked_unverified": "bad", "click_aborted": "bad", "edge_unsafe": "bad"}


def cli_command(*args):
    """Command line that runs this program's CLI (works from source and from the .exe)."""
    if config.FROZEN:
        return [sys.executable, *args]
    return [sys.executable, str(config.BASE_DIR / "bongo.py"), *args]


def fmt_left(sec):
    return "준비됨" if sec <= 0 else f"{sec // 60:02d}:{sec % 60:02d} 남음"


class Runner:
    """Owns the worker thread: capture -> engine.tick() -> events into a queue."""

    def __init__(self, cfg, db, events, make_engine=None):
        self.cfg, self.db, self.events = cfg, db, events
        self.make_engine = make_engine or self._real_engine
        self.engine = None
        self.error = None
        self._stop = threading.Event()
        self._thread = None

    def _real_engine(self, cap):
        import clicker
        import debug

        mon = cap.monitor(self.cfg["monitor"])
        templates = debug.load_templates(self.cfg, config.BASE_DIR)
        return engine_mod.Engine(self.cfg, lambda: cap.grab(self.cfg["monitor"], self.cfg["region"]),
                                 clicker.Clicker(), self.db, templates, monitor=mon,
                                 should_stop=self.should_stop)

    def should_stop(self):
        import clicker

        if clicker.stop_pressed():
            self._stop.set()
        return self._stop.is_set()

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self):
        self._stop.clear()
        self.error = None
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def join(self, timeout=10):
        if self._thread:
            self._thread.join(timeout)

    def _loop(self):
        cap = capture.Capturer()  # mss handles are per thread
        try:
            self.engine = self.make_engine(cap)
            self.engine.restore_timers()
            ocr.ensure_ready()
            while not self.should_stop():  # checked every cycle, even when a tick ran long
                t0 = time.time()
                for e in self.engine.tick():
                    self.events.put(e)
                while time.time() - t0 < self.cfg["interval_sec"] and not self.should_stop():
                    time.sleep(0.05)
        except Exception as e:  # surfaced in the UI; the loop must not die silently
            self.error = f"{type(e).__name__}: {e}"
        finally:
            cap.close()


class App:
    def __init__(self, root, cfg_path=config.CONFIG_PATH, base_dir=config.BASE_DIR, make_engine=None):
        self.root, self.cfg_path, self.base_dir = root, cfg_path, base_dir
        self.cfg = config.load(cfg_path)
        self.db = store_mod.Store(base_dir / "data" / "bongo.db")
        self.events = queue.Queue()
        self.runner = Runner(self.cfg, self.db, self.events, make_engine)
        self._build()
        self.refresh_chat()
        self._tick_ui()

    # ------------------------------------------------------------------ layout
    def _build(self):
        r = self.root
        r.title("Bongo Cat 헬퍼")
        r.geometry("1000x640")
        r.minsize(860, 520)
        style = ttk.Style(r)
        style.configure(".", font=("Malgun Gothic", 10))
        style.configure("Big.TLabel", font=("Malgun Gothic", 18, "bold"))
        style.configure("Accent.TButton", font=("Malgun Gothic", 10, "bold"))

        top = ttk.Frame(r, padding=8)
        top.pack(fill="x")
        self.btn_start = ttk.Button(top, text="시작", style="Accent.TButton", command=self.start)
        self.btn_stop = ttk.Button(top, text="정지(F12)", command=self.stop, state="disabled")
        self.btn_start.pack(side="left", padx=(0, 6))
        self.btn_stop.pack(side="left", padx=6)
        ttk.Button(top, text="보정", command=lambda: self.open_cli("setup")).pack(side="left", padx=6)
        ttk.Button(top, text="말풍선 보정", command=lambda: self.open_cli("setup", "--bubble")).pack(side="left", padx=6)
        ttk.Button(top, text="OCR 테스트", command=lambda: self.open_cli("test-ocr", "--watch", "30")).pack(side="left", padx=6)
        self.var_dry = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="dry run(연습 모드)", variable=self.var_dry).pack(side="left", padx=12)
        self.lbl_state = tk.Label(top, text="멈춤", bg="#e5e5e5", padx=12, pady=3, font=("Malgun Gothic", 10, "bold"))
        self.lbl_state.pack(side="right")

        body = ttk.Frame(r, padding=(8, 0, 8, 0))
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body, width=300)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        box = ttk.LabelFrame(left, text="선물 대상", padding=6)
        box.pack(fill="x")
        self.lst_targets = tk.Listbox(box, height=5, font=("Malgun Gothic", 10), exportselection=False)
        self.lst_targets.pack(fill="x")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(6, 0))
        self.ent_target = ttk.Entry(row)
        self.ent_target.pack(side="left", fill="x", expand=True)
        self.ent_target.bind("<Return>", lambda e: self.add_target())
        ttk.Button(row, text="추가", width=5, command=self.add_target).pack(side="left", padx=4)
        ttk.Button(row, text="삭제", width=5, command=self.remove_target).pack(side="left")
        self._show_targets()

        self.box_next = ttk.LabelFrame(left, text="다음 선물", padding=6)
        self.box_next.pack(fill="both", expand=True, pady=8)
        self.next_rows = []

        stats = ttk.LabelFrame(left, text="통계 (오늘)", padding=6)
        stats.pack(fill="x", pady=(0, 8))
        self.lbl_gifts = ttk.Label(stats, text="선물 0", style="Big.TLabel")
        self.lbl_chats = ttk.Label(stats, text="채팅 0", style="Big.TLabel")
        self.lbl_gifts.pack(side="left", expand=True)
        self.lbl_chats.pack(side="left", expand=True)

        tabs = ttk.Notebook(body)
        tabs.pack(side="left", fill="both", expand=True)
        log_tab = ttk.Frame(tabs, padding=6)
        chat_tab = ttk.Frame(tabs, padding=6)
        tabs.add(log_tab, text="판단 로그")
        tabs.add(chat_tab, text="채팅 기록")
        self.tabs = tabs

        self.txt_log = tk.Text(log_tab, font=("Consolas", 10), state="disabled", wrap="none")
        self.txt_log.pack(fill="both", expand=True)
        for tag, color in (("ok", "#1a7f37"), ("bad", "#c62828"), ("muted", "#777777"), ("chat", "#1f5fbf")):
            self.txt_log.tag_configure(tag, foreground=color)

        bar = ttk.Frame(chat_tab)
        bar.pack(fill="x", pady=(0, 6))
        self.cmb_date = ttk.Combobox(bar, width=12, state="readonly")
        self.cmb_speaker = ttk.Combobox(bar, width=12, state="readonly")
        self.ent_search = ttk.Entry(bar, width=18)
        self.cmb_date.pack(side="left")
        self.cmb_speaker.pack(side="left", padx=6)
        self.ent_search.pack(side="left", fill="x", expand=True)
        ttk.Button(bar, text="MD로 내보내기", command=self.export_chat).pack(side="right", padx=(6, 0))
        self.cmb_date.bind("<<ComboboxSelected>>", lambda e: self.refresh_chat(keep_date=True))
        self.cmb_speaker.bind("<<ComboboxSelected>>", lambda e: self.refresh_chat(keep_date=True))
        self.ent_search.bind("<KeyRelease>", lambda e: self.refresh_chat(keep_date=True))
        self.tree = ttk.Treeview(chat_tab, columns=("time", "who", "text"), show="headings")
        for col, title, width in (("time", "시간", 90), ("who", "화자", 100), ("text", "내용", 400)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, stretch=col == "text")
        self.tree.pack(fill="both", expand=True)

        self.lbl_status = ttk.Label(r, padding=(8, 4))
        self.lbl_status.pack(fill="x")

    # ------------------------------------------------------------------ targets
    def _show_targets(self):
        self.lst_targets.delete(0, "end")
        for t in self.cfg["targets"]:
            self.lst_targets.insert("end", t)

    def _save_cfg(self):
        config.save(self.cfg, self.cfg_path)

    def add_target(self, name=None):
        name = (name or self.ent_target.get()).strip()
        if name and name not in self.cfg["targets"]:
            self.cfg["targets"].append(name)
            self._save_cfg()
            self._show_targets()
        self.ent_target.delete(0, "end")

    def remove_target(self, name=None):
        if name is None:
            sel = self.lst_targets.curselection()
            if not sel:
                return
            name = self.lst_targets.get(sel[0])
        self.cfg["targets"] = [t for t in self.cfg["targets"] if t != name]
        self._save_cfg()
        self._show_targets()

    # ------------------------------------------------------------------ run
    def _ready_problem(self):
        if not self.cfg["region"][2] or not self.cfg["tag"]["height"]:
            return "보정이 아직 저장되지 않았습니다. [보정]을 먼저 해 주세요."
        if not self.cfg["targets"]:
            return "선물 대상을 한 명 이상 추가해 주세요."
        try:
            debug.load_templates(self.cfg, self.base_dir)
        except (FileNotFoundError, ValueError) as e:
            return str(e)
        return None

    def start(self, confirm=messagebox.askyesno):
        if self.runner.running:
            return
        fresh = config.load(self.cfg_path)  # pick up a setup done in the other window
        fresh["targets"] = self.cfg["targets"]
        self.cfg.clear()
        self.cfg.update(fresh)
        problem = self._ready_problem()
        if problem:
            messagebox.showwarning("시작할 수 없음", problem)
            return
        live = not self.var_dry.get()
        if live and not confirm("실제 클릭", "실제로 마우스를 클릭해서 선물을 보냅니다.\n대상: "
                                + ", ".join(self.cfg["targets"]) + "\n계속할까요?"):
            return
        self.cfg["dry_run"] = not live
        self.runner.start()
        self._set_running(True)

    def stop(self):
        self.runner.stop()

    def _set_running(self, on):
        self.btn_start.configure(state="disabled" if on else "normal")
        self.btn_stop.configure(state="normal" if on else "disabled")
        if on:
            dry = self.cfg["dry_run"]
            self.lbl_state.configure(text="연습 모드 · 실행 중" if dry else "실제 클릭 · 실행 중",
                                     bg="#fde68a" if dry else "#fecaca")
        else:
            self.lbl_state.configure(text="멈춤", bg="#e5e5e5")

    def open_cli(self, *args):
        if self.runner.running:
            messagebox.showinfo("실행 중", "먼저 정지한 뒤에 해 주세요.")
            return
        subprocess.Popen(cli_command(*args), cwd=str(self.base_dir), creationflags=subprocess.CREATE_NEW_CONSOLE)

    # ------------------------------------------------------------------ periodic UI work
    def _tick_ui(self):
        new_chat = False
        while True:
            try:
                e = self.events.get_nowait()
            except queue.Empty:
                break
            self._append_log(engine_mod.format_event(e), RESULT_TAG.get(e.result, ""))
            new_chat |= e.result == "chat"
        if new_chat:
            self.refresh_chat(keep_date=True)
        if str(self.btn_stop["state"]) == "normal" and not self.runner.running:
            self._set_running(False)
            if self.runner.error:
                self._append_log(f"오류로 멈춤: {self.runner.error}", "bad")
        self._refresh_countdown()
        self._refresh_stats()
        self.root.after(500, self._tick_ui)

    def _append_log(self, line, tag):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", line + "\n", tag)
        if int(self.txt_log.index("end-1c").split(".")[0]) > 2000:
            self.txt_log.delete("1.0", "500.0")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def countdown_rows(self, now=None):
        eng = self.runner.engine
        if not eng:
            return []
        now = now or time.time()
        targets = {ocr.normalize(t) for t in self.cfg["targets"]}
        return [r for r in eng.timers.upcoming(now) if r[0] in targets]

    def _refresh_countdown(self):
        rows = self.countdown_rows()
        while len(self.next_rows) < len(rows):
            f = ttk.Frame(self.box_next)
            f.pack(fill="x", pady=2)
            lbl = tk.Label(f, anchor="w", font=("Malgun Gothic", 10), width=20)
            bar = ttk.Progressbar(f, length=90, maximum=100)
            lbl.pack(side="left")
            bar.pack(side="right")
            self.next_rows.append((f, lbl, bar))
        while len(self.next_rows) > len(rows):
            self.next_rows.pop()[0].destroy()
        cooldown = self.cfg["gift_cooldown_sec"]
        for (f, lbl, bar), (name, side, left) in zip(self.next_rows, rows):
            lbl.configure(text=f"{name} {SIDE_KO[side]} · {fmt_left(left)}", fg="#1a7f37" if left <= 0 else "black")
            bar["value"] = 100 * (cooldown - left) / cooldown   # filled = time already waited

    def _refresh_stats(self):
        midnight = datetime.datetime.combine(datetime.date.today(), datetime.time()).timestamp()
        kinds = ("dry_run",) if self.cfg["dry_run"] else ("clicked_ok",)
        gifts = self.db.count_gifts(since=midnight, results=kinds)
        chats = self.db.count_chat(datetime.date.today().isoformat())
        self.lbl_gifts.configure(text=f"선물 {gifts}" + (" (연습)" if self.cfg["dry_run"] else ""))
        self.lbl_chats.configure(text=f"채팅 {chats}")
        self.lbl_status.configure(text=f"저장: data/bongo.db · 오늘 채팅 {chats}건 · 로그: logs/actions_날짜.txt")

    # ------------------------------------------------------------------ chat tab
    def chat_filter(self):
        date = self.cmb_date.get()
        speaker = self.cmb_speaker.get()
        return (None if date in ("", "전체 날짜") else date,
                None if speaker in ("", "전체") else speaker,
                self.ent_search.get().strip() or None)

    def refresh_chat(self, keep_date=False):
        dates = self.db.chat_dates()
        if not keep_date:
            self.cmb_date["values"] = ["전체 날짜", *dates]
            self.cmb_date.set(dates[-1] if dates else "전체 날짜")
        date, _, _ = self.chat_filter()
        speakers = self.db.chat_speakers(date)
        self.cmb_speaker["values"] = ["전체", *speakers]
        if self.cmb_speaker.get() not in self.cmb_speaker["values"]:
            self.cmb_speaker.set("전체")
        self.tree.delete(*self.tree.get_children())
        for ts, speaker, text in self.db.query_chat(*self.chat_filter()):
            self.tree.insert("", "end", values=(time.strftime("%H:%M:%S", time.localtime(ts)), speaker, text))

    def export_chat(self, notify=messagebox.showinfo):
        date, speaker, keyword = self.chat_filter()
        rows = self.db.query_chat(date, speaker, keyword)
        if not rows:
            notify("내보내기", "내보낼 채팅이 없습니다.")
            return None
        path = chatlog.export_md(rows, self.base_dir / "exports", " ".join(x for x in (speaker, keyword) if x))
        notify("내보내기", f"저장했습니다:\n{path}")
        return path

    def close(self):
        self.runner.stop()
        self.runner.join()  # a running tick may still write to the DB or click
        if not self.runner.running:  # still busy after the wait: leave the DB to process exit
            self.db.close()
        self.root.destroy()


def main():
    capture.set_dpi_aware()
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()
