
# VasoFlux
<img width="1200" height="1600" alt="image" src="https://github.com/user-attachments/assets/fde083a7-16f4-4807-ac6e-b0e02d06e0ef" />

A web-based cognitive monitoring platform paired with a physical prototype for non-invasive, low-cost CO₂ monitoring via transcutaneous diffusion. The prototype was built using Arduino and detects CO₂ levels through diffused gas captured at the skin surface. The platform uses eye-tracking and validated psychological assessments to identify early cognitive decline associated with hypercapnia in COPD patients.

# Hypercapnia Early Detection — Cognitive Screening Tools

Two complementary tools for non-invasive cognitive screening of hypercapnia risk in COPD patients using eye tracking, biometric monitoring, and psychological assessments.

---

## Files

| File | Description |
|------|-------------|
| `hypercapnia_monitor.py` | Desktop app — live camera monitoring with passive biometrics + active cognitive tests |
| `hypercapnia_screening.html` | Web app — browser-based 5-step screening using MediaPipe, no install required |

---

## hypercapnia_monitor.py

A Python desktop application that continuously monitors a patient via webcam and computes a real-time hypercapnia risk score.

### How it works

**Passive monitoring (runs continuously):**
- Eye Aspect Ratio (EAR) — detects drooping eyelids, a known hypercapnia symptom
- Blink rate — reduced blinking correlates with CO₂-induced drowsiness
- Breathing rate — estimated from chest pixel movement in the camera frame

**Active cognitive tests (every 5 minutes):**
- Response time test — patient reads a sentence and presses Space
- Stroop test — patient identifies ink color of a color word (3 trials)

**Risk score:**
Weighted combination of all five signals (0–100). Thresholds: Normal < 40, Elevated 40–70, High ≥ 70.

### Requirements

```
pip install opencv-python mediapipe pillow numpy
```

Tkinter is included with standard Python on Windows and macOS. On Linux:
```
sudo apt install python3-tk
```

### Run

```
python hypercapnia_monitor.py
```

Requires a working webcam. Keep your face visible and well lit for best results.

---

## hypercapnia_screening.html

A browser-based 5-step screening tool. No installation required — just open in Chrome or Edge.

### Steps

1. **Symptom survey** — 6 questions about headache, fatigue, confusion, shortness of breath, and recent COPD episodes
2. **Eye tracking calibration** — MediaPipe face mesh measures eye openness baseline via webcam
3. **Breath hold test** — timed breath hold with waveform visualization
4. **Stroop cognitive test** — identify ink color of mismatched color words, measures response time
5. **Results** — combined risk score with individual component breakdown and recommendation

### How to run

Just open the file directly in Chrome or Edge:
```
double-click hypercapnia_screening.html
```

Or serve it locally to avoid camera permission issues:
```
python -m http.server 8080
```
Then open `http://localhost:8080/hypercapnia_screening.html`

**Note:** Camera access requires either a local server or HTTPS. Opening directly as a file may block camera in some browsers.

---

## How this fits into VasoFlux

These tools serve as a **cognitive screening layer** alongside the VasoFlux wrist device:

- The wrist device measures **physiological CO₂** via transcutaneous diffusion
- These tools detect **cognitive and behavioral patterns** consistent with hypercapnia
- Together they form a dual-modality detection system — hardware + software

Hypercapnia causes measurable cognitive slowing before patients feel symptoms. Flagging these patterns prompts the patient to run a device scan, enabling earlier detection.

---

## Notes

- These tools are screening aids, not diagnostic replacements for arterial blood gas testing
- Results should be reviewed by a qualified clinician
- Cognitive baselines are calibrated on first use — accuracy improves after the first session
