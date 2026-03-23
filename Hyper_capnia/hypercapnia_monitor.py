"""
Hypercapnia Early Detection Monitor for COPD Patients
------------------------------------------------------
Passive biometric monitoring + active cognitive tests
to detect early signs of CO2 retention via laptop camera.
"""

import cv2
import mediapipe as mp
import tkinter as tk
from tkinter import ttk, font as tkfont
import threading
import time
import random
import math
import collections
from PIL import Image, ImageTk
import numpy as np

# ── MediaPipe setup ───────────────────────────────────────────────────────────
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)

LEFT_EYE  = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [ 33, 160, 158, 133, 153, 144]

# ── Constants ─────────────────────────────────────────────────────────────────
EAR_BLINK_THRESHOLD = 0.21   # below this → eyes closed (blink)
COGNITIVE_TEST_INTERVAL = 300  # seconds between active tests (5 min)
HISTORY_SECONDS = 600          # 10-minute rolling window for graph

COLORS = {
    "bg":       "#0d1117",
    "panel":    "#161b22",
    "border":   "#30363d",
    "text":     "#e6edf3",
    "subtext":  "#8b949e",
    "green":    "#3fb950",
    "yellow":   "#d29922",
    "red":      "#f85149",
    "blue":     "#58a6ff",
    "accent":   "#1f6feb",
}

STROOP_WORDS  = ["RED", "GREEN", "BLUE"]
STROOP_COLORS = {
    "RED":   "#e74c3c",
    "GREEN": "#2ecc71",
    "BLUE":  "#3498db",
}
KEY_COLOR_MAP = {"r": "RED", "g": "GREEN", "b": "BLUE"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def clamp(val):
    return max(0.0, min(100.0, float(val)))


def eye_aspect_ratio(landmarks, eye_pts, w, h):
    coords = [(int(landmarks[i].x * w), int(landmarks[i].y * h)) for i in eye_pts]
    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])
    v1 = dist(coords[1], coords[5])
    v2 = dist(coords[2], coords[4])
    hz = dist(coords[0], coords[3])
    return (v1 + v2) / (2.0 * hz) if hz > 0 else 0.0


# ── Core monitoring state ─────────────────────────────────────────────────────

class MonitorState:
    def __init__(self):
        self.lock = threading.Lock()

        # Live biometrics
        self.avg_ear        = 0.30
        self.blink_rate     = 15.0   # blinks/min
        self.breath_rate    = 16.0   # breaths/min

        # Cognitive scores (normalized 0-100)
        self.response_score = 0.0
        self.stroop_score   = 0.0

        # Calibration baselines
        self.baseline_response_ms = None  # set after first cognitive test
        self.baseline_stroop_ms   = None

        # Blink tracking
        self._blink_times: collections.deque = collections.deque()
        self._eye_closed = False

        # Breathing: track chest pixel column intensity over time
        self._breath_buffer: collections.deque = collections.deque(maxlen=300)

        # Risk history for graph (timestamp, score)
        self.risk_history: collections.deque = collections.deque()

        # Computed
        self.risk_score = 0.0
        self.risk_level = "NORMAL"

        # Session
        self.patient_name  = "Patient"
        self.session_start = time.time()

    # ── Blink tracking ────────────────────────────────────────────────────────

    def update_ear(self, ear):
        now = time.time()
        with self.lock:
            self.avg_ear = ear
            if ear < EAR_BLINK_THRESHOLD:
                if not self._eye_closed:
                    self._eye_closed = True
                    self._blink_times.append(now)
            else:
                self._eye_closed = False

            # Drop blinks older than 60 s
            cutoff = now - 60.0
            while self._blink_times and self._blink_times[0] < cutoff:
                self._blink_times.popleft()
            self.blink_rate = len(self._blink_times)  # blinks in last 60 s = blinks/min

    # ── Breathing tracking ────────────────────────────────────────────────────

    def update_breath(self, frame):
        """
        Sample mean brightness of the upper-chest region (rows 55-75% of frame,
        centre third horizontally) to detect chest rise/fall.
        """
        h, w = frame.shape[:2]
        r0, r1 = int(h * 0.55), int(h * 0.75)
        c0, c1 = int(w * 0.33), int(w * 0.66)
        roi = frame[r0:r1, c0:c1]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        val = float(np.mean(gray))
        with self.lock:
            self._breath_buffer.append(val)
            # Count zero-crossings of the mean-subtracted signal → breath cycles
            buf = list(self._breath_buffer)
            if len(buf) >= 60:
                mean = sum(buf) / len(buf)
                centered = [v - mean for v in buf]
                crossings = sum(
                    1 for i in range(1, len(centered))
                    if centered[i - 1] < 0 < centered[i]
                )
                # Each crossing = half cycle; 30 fps buffer → duration in seconds
                duration_s = len(buf) / 30.0
                self.breath_rate = max(4.0, (crossings / duration_s) * 60.0 / 2.0)

    # ── Risk score computation ────────────────────────────────────────────────

    def compute_risk(self):
        with self.lock:
            ear       = clamp(((0.30 - self.avg_ear)   / 0.10) * 100)
            blink     = clamp(((15   - self.blink_rate) / 10)  * 100)
            breath    = clamp(((self.breath_rate - 18)  / 10)  * 100)
            response  = clamp(self.response_score)
            stroop    = clamp(self.stroop_score)

            score = (
                ear      * 0.25 +
                blink    * 0.20 +
                response * 0.20 +
                breath   * 0.20 +
                stroop   * 0.15
            )
            self.risk_score = score

            if score >= 70:
                self.risk_level = "HIGH"
            elif score >= 40:
                self.risk_level = "ELEVATED"
            else:
                self.risk_level = "NORMAL"

            now = time.time()
            self.risk_history.append((now, score))
            cutoff = now - HISTORY_SECONDS
            while self.risk_history and self.risk_history[0][0] < cutoff:
                self.risk_history.popleft()

            return score, self.risk_level, ear, blink, breath, response, stroop


# ── Active cognitive test window ──────────────────────────────────────────────

class CognitiveTestWindow:
    """
    Runs a two-phase active test:
      Phase 1 – response time (read sentence, press Space)
      Phase 2 – Stroop test (3 trials)
    Updates MonitorState when done.
    """

    SENTENCE = "The patient breathes slowly and feels calm today."

    def __init__(self, parent_root, state: MonitorState):
        self.state = state
        self.win = tk.Toplevel(parent_root)
        self.win.title("Cognitive Test")
        self.win.configure(bg=COLORS["bg"])
        self.win.geometry("700x420")
        self.win.resizable(False, False)
        self.win.grab_set()

        self._phase = 1
        self._rt_start = None
        self._rt_results = []
        self._stroop_results = []
        self._stroop_trial = 0
        self._stroop_start = None
        self._current_word  = None
        self._current_color = None
        self._correct_key   = None
        self._total_stroop  = 3

        self._build_ui()
        self._start_phase1()

    def _build_ui(self):
        self.title_lbl = tk.Label(self.win, text="Cognitive Assessment",
                                  bg=COLORS["bg"], fg=COLORS["blue"],
                                  font=("Segoe UI", 16, "bold"))
        self.title_lbl.pack(pady=(20, 6))

        self.sub_lbl = tk.Label(self.win, text="",
                                bg=COLORS["bg"], fg=COLORS["subtext"],
                                font=("Segoe UI", 10))
        self.sub_lbl.pack()

        self.content_frame = tk.Frame(self.win, bg=COLORS["bg"])
        self.content_frame.pack(expand=True, fill="both", padx=40)

        self.main_lbl = tk.Label(self.content_frame, text="",
                                 bg=COLORS["bg"], fg=COLORS["text"],
                                 font=("Segoe UI", 15), wraplength=600,
                                 justify="center")
        self.main_lbl.pack(expand=True)

        self.hint_lbl = tk.Label(self.win, text="",
                                 bg=COLORS["bg"], fg=COLORS["subtext"],
                                 font=("Segoe UI", 10))
        self.hint_lbl.pack(pady=(0, 20))

        self.win.bind("<space>",  self._on_space)
        self.win.bind("<KeyPress>", self._on_key)

    # ── Phase 1: response time ────────────────────────────────────────────────

    def _start_phase1(self):
        self._phase = 1
        self.sub_lbl.config(text="Phase 1 of 2 — Reading Speed")
        self.main_lbl.config(text=self.SENTENCE, fg=COLORS["text"])
        self.hint_lbl.config(text="Press SPACEBAR as soon as you finish reading")
        self._rt_start = time.time()

    def _on_space(self, event):
        if self._phase == 1 and self._rt_start:
            rt_ms = (time.time() - self._rt_start) * 1000
            self._rt_results.append(rt_ms)
            self._update_response_score(rt_ms)
            self._start_phase2()

    def _update_response_score(self, rt_ms):
        st = self.state
        with st.lock:
            if st.baseline_response_ms is None:
                st.baseline_response_ms = rt_ms
                st.response_score = 0.0
            else:
                ratio = rt_ms / st.baseline_response_ms
                st.response_score = clamp(((ratio - 1.0) / 0.5) * 100)

    # ── Phase 2: Stroop ───────────────────────────────────────────────────────

    def _start_phase2(self):
        self._phase = 2
        self._stroop_trial = 0
        self.sub_lbl.config(text="Phase 2 of 2 — Color-Word Interference (Stroop)")
        self.hint_lbl.config(
            text="Press  R = Red   G = Green   B = Blue  for the INK COLOR (not the word)"
        )
        self._next_stroop_trial()

    def _next_stroop_trial(self):
        if self._stroop_trial >= self._total_stroop:
            self._finish()
            return
        word  = random.choice(STROOP_WORDS)
        # Pick a color different from the word for incongruent trials
        others = [c for c in STROOP_WORDS if c != word]
        color = random.choice(others)
        self._current_word  = word
        self._current_color = color
        self._correct_key   = color[0].lower()  # 'r', 'g', or 'b'
        self.main_lbl.config(text=word, fg=STROOP_COLORS[color],
                             font=("Segoe UI", 42, "bold"))
        self.sub_lbl.config(
            text=f"Phase 2 of 2 — Trial {self._stroop_trial + 1} of {self._total_stroop}"
        )
        self._stroop_start = time.time()

    def _on_key(self, event):
        if self._phase != 2:
            return
        key = event.keysym.lower()
        if key not in KEY_COLOR_MAP:
            return
        elapsed_ms = (time.time() - self._stroop_start) * 1000
        correct = (key == self._correct_key)
        self._stroop_results.append({"ms": elapsed_ms, "correct": correct})
        self._stroop_trial += 1
        self._next_stroop_trial()

    def _finish(self):
        if self._stroop_results:
            avg_ms   = sum(r["ms"] for r in self._stroop_results) / len(self._stroop_results)
            accuracy = sum(1 for r in self._stroop_results if r["correct"]) / len(self._stroop_results)
            # Penalise inaccuracy by inflating the effective time
            effective_ms = avg_ms / max(0.01, accuracy)
            st = self.state
            with st.lock:
                if st.baseline_stroop_ms is None:
                    st.baseline_stroop_ms = effective_ms
                    st.stroop_score = 0.0
                else:
                    ratio = effective_ms / st.baseline_stroop_ms
                    st.stroop_score = clamp(((ratio - 1.0) / 0.5) * 100)

        self.main_lbl.config(text="Test complete. Thank you.", fg=COLORS["green"],
                             font=("Segoe UI", 15))
        self.hint_lbl.config(text="This window will close in 3 seconds.")
        self.win.after(3000, self.win.destroy)


# ── Main dashboard ────────────────────────────────────────────────────────────

class HypercapniaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Hypercapnia Early Detection Monitor")
        self.root.configure(bg=COLORS["bg"])
        self.root.geometry("1200x760")
        self.root.minsize(1100, 700)

        self.state = MonitorState()
        self._cap  = None
        self._running = True
        self._last_test_time = time.time()
        self._test_active = False

        self._build_ui()
        self._start_camera_thread()
        self._schedule_ui_update()
        self._schedule_cognitive_test()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ──────────────────────────────────────────────────────────
        topbar = tk.Frame(self.root, bg=COLORS["panel"], height=56)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        tk.Label(topbar, text="⬤  Hypercapnia Monitor",
                 bg=COLORS["panel"], fg=COLORS["blue"],
                 font=("Segoe UI", 14, "bold")).pack(side="left", padx=20, pady=14)

        # Patient name
        tk.Label(topbar, text="Patient:", bg=COLORS["panel"],
                 fg=COLORS["subtext"], font=("Segoe UI", 10)).pack(side="left", padx=(30, 4))
        self._name_var = tk.StringVar(value="Patient")
        name_entry = tk.Entry(topbar, textvariable=self._name_var,
                              bg=COLORS["border"], fg=COLORS["text"],
                              insertbackground=COLORS["text"],
                              relief="flat", font=("Segoe UI", 10), width=18)
        name_entry.pack(side="left")
        name_entry.bind("<Return>", lambda e: self.state.__setattr__(
            "patient_name", self._name_var.get()))

        self._session_lbl = tk.Label(topbar, text="Session: 00:00",
                                     bg=COLORS["panel"], fg=COLORS["subtext"],
                                     font=("Segoe UI", 10))
        self._session_lbl.pack(side="right", padx=20)

        # ── Main body ─────────────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=12, pady=12)

        # Left column: camera + graph
        left = tk.Frame(body, bg=COLORS["bg"])
        left.pack(side="left", fill="both", expand=True)

        self._cam_label = tk.Label(left, bg="#000000",
                                   relief="flat", bd=0)
        self._cam_label.pack(fill="x")

        graph_panel = self._panel(left, "Risk Score — Last 10 Minutes")
        graph_panel.pack(fill="both", expand=True, pady=(10, 0))
        self._graph_canvas = tk.Canvas(graph_panel, bg=COLORS["bg"],
                                       highlightthickness=0, height=130)
        self._graph_canvas.pack(fill="both", expand=True, padx=10, pady=8)

        # Right column: scores + risk
        right = tk.Frame(body, bg=COLORS["bg"], width=320)
        right.pack(side="right", fill="y", padx=(12, 0))
        right.pack_propagate(False)

        # Central risk badge
        risk_panel = self._panel(right, "Overall Risk")
        risk_panel.pack(fill="x")

        self._risk_score_lbl = tk.Label(risk_panel, text="0",
                                        bg=COLORS["panel"], fg=COLORS["green"],
                                        font=("Segoe UI", 64, "bold"))
        self._risk_score_lbl.pack()

        self._risk_level_lbl = tk.Label(risk_panel, text="NORMAL",
                                        bg=COLORS["panel"], fg=COLORS["green"],
                                        font=("Segoe UI", 14, "bold"))
        self._risk_level_lbl.pack()

        self._recommendation_lbl = tk.Label(risk_panel,
                                            text="Continue monitoring",
                                            bg=COLORS["panel"], fg=COLORS["subtext"],
                                            font=("Segoe UI", 9),
                                            wraplength=280, justify="center")
        self._recommendation_lbl.pack(pady=(2, 10))

        # Signal bars
        signals_panel = self._panel(right, "Signal Details")
        signals_panel.pack(fill="x", pady=(10, 0))

        self._bars = {}
        signals = [
            ("ear",      "Eye Aspect Ratio",  0.25),
            ("blink",    "Blink Rate",         0.20),
            ("breath",   "Breathing Rate",     0.20),
            ("response", "Response Time",      0.20),
            ("stroop",   "Stroop Test",        0.15),
        ]
        for key, label, weight in signals:
            self._bars[key] = self._make_bar(signals_panel, label, weight)

        # Next test countdown
        self._test_lbl = tk.Label(right, text="Next test in: 5:00",
                                  bg=COLORS["bg"], fg=COLORS["subtext"],
                                  font=("Segoe UI", 9))
        self._test_lbl.pack(pady=(8, 0))

        # Manual trigger
        tk.Button(right, text="Run Test Now",
                  bg=COLORS["accent"], fg="white",
                  activebackground=COLORS["blue"],
                  relief="flat", font=("Segoe UI", 10, "bold"),
                  cursor="hand2",
                  command=self._trigger_test).pack(pady=(4, 0), ipadx=10, ipady=4)

    def _panel(self, parent, title):
        frame = tk.Frame(parent, bg=COLORS["panel"],
                         highlightbackground=COLORS["border"],
                         highlightthickness=1)
        tk.Label(frame, text=title, bg=COLORS["panel"],
                 fg=COLORS["subtext"], font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=10, pady=(8, 2))
        return frame

    def _make_bar(self, parent, label, weight):
        row = tk.Frame(parent, bg=COLORS["panel"])
        row.pack(fill="x", padx=10, pady=3)

        tk.Label(row, text=label, bg=COLORS["panel"], fg=COLORS["text"],
                 font=("Segoe UI", 9), width=18, anchor="w").pack(side="left")

        bar_bg = tk.Frame(row, bg=COLORS["border"], height=10, width=140)
        bar_bg.pack(side="left", padx=(4, 6))
        bar_bg.pack_propagate(False)

        bar_fill = tk.Frame(bar_bg, bg=COLORS["green"], height=10, width=0)
        bar_fill.place(x=0, y=0, height=10, width=0)

        val_lbl = tk.Label(row, text="0", bg=COLORS["panel"],
                           fg=COLORS["subtext"], font=("Segoe UI", 9), width=4)
        val_lbl.pack(side="left")

        return {"bg": bar_bg, "fill": bar_fill, "val": val_lbl}

    # ── Camera thread ─────────────────────────────────────────────────────────

    def _start_camera_thread(self):
        t = threading.Thread(target=self._camera_loop, daemon=True)
        t.start()

    def _camera_loop(self):
        self._cap = cv2.VideoCapture(0)
        while self._running:
            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb)

            if results.multi_face_landmarks:
                lm = results.multi_face_landmarks[0].landmark
                left_ear  = eye_aspect_ratio(lm, LEFT_EYE,  w, h)
                right_ear = eye_aspect_ratio(lm, RIGHT_EYE, w, h)
                avg_ear   = (left_ear + right_ear) / 2.0
                self.state.update_ear(avg_ear)

                # Draw eye landmarks
                for idx in LEFT_EYE + RIGHT_EYE:
                    x = int(lm[idx].x * w)
                    y = int(lm[idx].y * h)
                    cv2.circle(frame, (x, y), 2, (0, 220, 255), -1)

            self.state.update_breath(frame)

            # Overlay text
            with self.state.lock:
                ear_v    = self.state.avg_ear
                br_v     = self.state.breath_rate
                bk_v     = self.state.blink_rate
                rs_v     = self.state.risk_score
                rl_v     = self.state.risk_level

            color_map = {"NORMAL": (80, 200, 80), "ELEVATED": (0, 180, 220), "HIGH": (60, 60, 220)}
            oc = color_map.get(rl_v, (200, 200, 200))

            cv2.putText(frame, f"EAR: {ear_v:.3f}", (10, 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 100), 1)
            cv2.putText(frame, f"BR: {br_v:.1f}/min", (10, 48),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 100), 1)
            cv2.putText(frame, f"Blink: {bk_v:.0f}/min", (10, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 100), 1)
            cv2.putText(frame, f"Risk: {rs_v:.0f}  {rl_v}", (10, 94),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, oc, 2)

            # Store frame for UI
            self._latest_frame = frame
            time.sleep(0.033)  # ~30 fps

        self._cap.release()

    # ── UI update loop ────────────────────────────────────────────────────────

    def _schedule_ui_update(self):
        self._update_ui()
        self.root.after(200, self._schedule_ui_update)

    def _update_ui(self):
        # Camera feed
        frame = getattr(self, "_latest_frame", None)
        if frame is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            img = img.resize((640, 360), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._cam_label.configure(image=photo)
            self._cam_label.image = photo

        # Compute risk
        score, level, ear, blink, breath, response, stroop = self.state.compute_risk()
        subs = {
            "ear":      ear,
            "blink":    blink,
            "breath":   breath,
            "response": response,
            "stroop":   stroop,
        }
        for key, val in subs.items():
            self._update_bar(key, val)

        # Risk badge colour
        color = (
            COLORS["red"]    if level == "HIGH"
            else COLORS["yellow"] if level == "ELEVATED"
            else COLORS["green"]
        )
        rec = {
            "HIGH":     "Seek immediate medical attention",
            "ELEVATED": "Monitor closely, consider clinical assessment",
            "NORMAL":   "Continue monitoring",
        }.get(level, "")

        self._risk_score_lbl.config(text=f"{score:.0f}", fg=color)
        self._risk_level_lbl.config(text=level, fg=color)
        self._recommendation_lbl.config(text=rec)

        # Session timer
        elapsed = int(time.time() - self.state.session_start)
        m, s = divmod(elapsed, 60)
        self._session_lbl.config(text=f"Session: {m:02d}:{s:02d}")

        # Next test countdown
        since_test = time.time() - self._last_test_time
        remaining  = max(0, COGNITIVE_TEST_INTERVAL - since_test)
        tm, ts = divmod(int(remaining), 60)
        self._test_lbl.config(text=f"Next test in: {tm}:{ts:02d}")

        # Graph
        self._draw_graph()

    def _update_bar(self, key, val):
        bar = self._bars[key]
        bg_w = bar["bg"].winfo_width() or 140
        fill_w = int((val / 100) * bg_w)
        color = (
            COLORS["red"]    if val >= 70
            else COLORS["yellow"] if val >= 40
            else COLORS["green"]
        )
        bar["fill"].place(x=0, y=0, height=10, width=fill_w)
        bar["fill"].config(bg=color)
        bar["val"].config(text=f"{val:.0f}")

    def _draw_graph(self):
        c = self._graph_canvas
        c.delete("all")
        cw = c.winfo_width()
        ch = c.winfo_height()
        if cw < 10 or ch < 10:
            return

        history = list(self.state.risk_history)
        if len(history) < 2:
            c.create_text(cw // 2, ch // 2, text="Collecting data…",
                          fill=COLORS["subtext"], font=("Segoe UI", 9))
            return

        pad = 30
        now = time.time()
        t_min = now - HISTORY_SECONDS

        def to_x(t):
            return pad + (t - t_min) / HISTORY_SECONDS * (cw - 2 * pad)

        def to_y(v):
            return ch - pad - (v / 100) * (ch - 2 * pad)

        # Grid lines + labels
        for score_line, label in [(0, "0"), (40, "40"), (70, "70"), (100, "100")]:
            y = to_y(score_line)
            lc = COLORS["yellow"] if score_line == 40 else (
                 COLORS["red"]    if score_line == 70 else COLORS["border"])
            c.create_line(pad, y, cw - pad, y, fill=lc, dash=(3, 4))
            c.create_text(pad - 4, y, text=label, fill=COLORS["subtext"],
                          font=("Segoe UI", 7), anchor="e")

        # Plot line
        points = [(to_x(t), to_y(v)) for t, v in history]
        for i in range(1, len(points)):
            x0, y0 = points[i - 1]
            x1, y1 = points[i]
            v = history[i][1]
            col = (COLORS["red"] if v >= 70 else
                   COLORS["yellow"] if v >= 40 else COLORS["green"])
            c.create_line(x0, y0, x1, y1, fill=col, width=2)

        # Latest value dot
        if points:
            lx, ly = points[-1]
            lv = history[-1][1]
            col = (COLORS["red"] if lv >= 70 else
                   COLORS["yellow"] if lv >= 40 else COLORS["green"])
            c.create_oval(lx - 4, ly - 4, lx + 4, ly + 4, fill=col, outline="")

    # ── Cognitive test scheduling ─────────────────────────────────────────────

    def _schedule_cognitive_test(self):
        self.root.after(COGNITIVE_TEST_INTERVAL * 1000, self._auto_trigger_test)

    def _auto_trigger_test(self):
        self._trigger_test()
        self._schedule_cognitive_test()

    def _trigger_test(self):
        if self._test_active:
            return
        self._test_active = True
        self._last_test_time = time.time()

        def run():
            win = CognitiveTestWindow(self.root, self.state)
            self.root.wait_window(win.win)
            self._test_active = False

        self.root.after(0, run)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def _on_close(self):
        self._running = False
        self.root.after(200, self.root.destroy)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    app  = HypercapniaApp(root)
    root.mainloop()
