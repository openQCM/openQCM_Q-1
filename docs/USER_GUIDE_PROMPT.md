# Prompt for AI: Generate the openQCM Q-1 v3.0 User Guide

## Role

You are a technical writer producing a comprehensive end-user guide for the openQCM Q-1 software v3.0. You will receive two input files:

1. **USER_GUIDE_BRIEF.md** — the primary technical reference (feature descriptions, workflows, file formats, troubleshooting)
2. **This file** — corrections to the brief, supplementary context, output requirements, and editorial guidelines

**This file takes precedence over the brief wherever they conflict.**

---

## 1. Corrections to USER_GUIDE_BRIEF.md

Apply these corrections before generating the guide:

| Brief section | What to fix |
|---|---|
| §1 Product Overview | Software version is **3.0** (remove "dev") |
| §1 Product Overview | Add: "Quartz Crystal Microbalance with Dissipation monitoring" as the full instrument descriptor |
| §2 Dependencies | Remove `matplotlib` from the dependency list — it is not required at runtime and is excluded from the standalone build |
| §2 Launch | The entry point is `python run.py`, not `python app.py` |
| §4 Menu Bar | The menu structure is **File / View / Tools / Help** (not View / Data / Help). See §3 below for the exact layout |
| §6.2 Right-click menu | Add **Show/Hide Grid** to the context menu items. Grid is OFF by default in all plots |
| §9.1 Tracking Safety | Re-enable requires **5 consecutive good sweeps** (not a single good sweep). Asymmetric hysteresis: 10 bad to disable, 5 good to re-enable |
| §13.2 Software Updates | "Check for Updates" uses `urllib.request` + `html.parser` (stdlib), not pandas. Works in both source and frozen build |
| §17 Known Limitations | Remove the item about "9th overtone parameters are placeholders" — this is an internal development note, not relevant to end users |
| §18 Version History | CHANGELOG now contains **12 parts** (not 8). Parts 9-12 cover: tracking safety + signal quality + buffer statistics, code cleanup + public release prep, Windows standalone distribution, splash + hysteresis + plots + build polish |

---

## 2. Product identity — use consistently throughout

- **Full name**: openQCM Q-1 Quartz Crystal Microbalance with Dissipation monitoring
- **Short name**: openQCM Q-1
- **Software version**: 3.0
- **Firmware version**: 2.2
- **Vendor**: openQCM / Novaetech S.r.l.
- **Website**: https://openqcm.com/
- **Product page**: https://openqcm.com/about-openqcm-q-1
- **Repository**: https://github.com/openQCM/openQCM_Q-1
- **License**: GPLv3
- **Contact**: info@openqcm.com

---

## 3. Correct menu bar structure

```
File
├── Open Log…               (Ctrl+O / Cmd+O)
├── ─────────
└── Quit                    (Ctrl+Q / Cmd+Q)

View
├── Left Panel              (checkable, on by default)
├── Status Bar              (checkable, on by default)
├── Cursors                 (checkable, off by default)
├── ─────────
└── Theme ►
    ├── Dark Theme          (default, radio)
    └── Light Theme         (radio)

Tools
├── Measurement Parameters
├── Raw Data View
├── Peak Data View
├── ─────────
└── Check Firmware Version

Help
├── User Guide
├── Website
├── Email Support
├── ─────────
├── Check for Updates…
├── Download Update         (disabled until update detected)
├── ─────────
└── About openQCM Q-1
```

---

## 4. Available screenshots

The following screenshots are available in `docs/images/`. Reference them in the guide with the exact filenames:

| Filename | Description |
|---|---|
| `screenshot.png` | Main window, dark theme, during acquisition |
| `screenshot_dark.png` | Main window, dark theme variant |
| `screenshot_dark_grid.png` | Main window, dark theme with grid enabled |
| `screenshot_light.png` | Main window, light theme |
| `screenshot_light_grid.png` | Main window, light theme with grid enabled |

Use `![Figure: description](docs/images/filename.png)` syntax. For dialogs and close-ups not yet captured, use placeholder syntax: `![Figure: description — screenshot pending]`.

---

## 5. Windows standalone executable

The software is distributed in two forms — this must be documented:

### From Python source (developers / advanced users)
```
conda activate openqcm
python run.py
```

### Windows standalone (end users)
- Download the release zip from GitHub Releases
- Extract to any folder
- Run `openQCM_Q-1.exe`
- No Python installation required
- A splash screen is shown during first-time extraction (~5-15 seconds)
- Runtime directories (`openQCM/`, `logged_data/`) are created automatically on first run

---

## 6. Output requirements

- **Format**: Microsoft Word document (`.docx`), with proper heading styles (Heading 1 for chapters, Heading 2 for sections, Heading 3 for subsections) so that a Table of Contents can be auto-generated
- **Length**: 25–40 pages (3000–6000 words of prose, excluding tables and image placeholders)
- **Language**: English
- **Filename**: `openQCM_Q-1_User_Guide_v3.0.docx`
- **Structure**: Use a numbered chapter system (1. Introduction, 2. Installation, …)
- **Table of Contents**: Include on the second page (after a title page) using Word's built-in TOC field
- **Title page**: Include product name ("openQCM Q-1 Quartz Crystal Microbalance with Dissipation monitoring"), version (3.0), the openQCM logo placeholder, vendor (Novaetech S.r.l.), and date
- **Image placeholders**: Where a screenshot or diagram would help the reader, insert a clearly labeled placeholder box with the format:

  ```
  ┌──────────────────────────────────────────────┐
  │  [Figure N: Brief description of the image]  │
  │                                               │
  │  Suggested source: filename.png or            │
  │  "capture from application"                   │
  └──────────────────────────────────────────────┘
  ```

  For the 5 screenshots already available in `docs/images/`, reference them by filename. For all others, describe exactly what to capture so the images can be produced later.

- **Page headers/footers**: Header with "openQCM Q-1 — User Guide v3.0", footer with page number

---

## 7. Chapter outline (suggested)

1. **Introduction** — What is QCM, what does the openQCM Q-1 measure, what is this software
2. **Installation** — Python source setup (conda, pip, Linux permissions, Apple Silicon) AND Windows standalone
3. **Quick Start** — From "plug in the device" to "data flowing" in 6 steps
4. **Main Window Layout** — Three-zone description with annotated screenshot reference
5. **Menu Reference** — File, View, Tools, Help — every item described
6. **Peak Detection (Calibration)** — What it does, how to run it, how to read the results, troubleshooting
7. **Measurement Mode** — Starting acquisition, choosing overtones, setting reference, reading plots
8. **Real-Time Plots** — Amplitude/Phase, Frequency/Dissipation, Temperature; axes, legends, grid, zoom/pan
9. **Data Analysis Tools** — Raw Data View, Peak Data View, Log Data View, Measurement Cursors
10. **Auto-Tracking** — Drift compensation, safety hysteresis, sensor disconnect detection
11. **Data Logging and File Formats** — CSV structure, calibration files, filenames
12. **Firmware Check and Updates** — How the version check works, updater workflow
13. **Settings and Preferences** — Themes, tooltips, window size, axis lock/unlock
14. **Troubleshooting** — Common problems and solutions (from the brief §14)
15. **Appendix A: Keyboard and Mouse Reference** — Table from the brief §16
16. **Appendix B: Glossary** — Terms from the brief §20
17. **Appendix C: Advanced CLI Tools** — peak_detection_analyzer, overtone_analyzer, sampling_time_monitor

---

## 8. Editorial guidelines

- **Tone**: Technical, instructional, concise. This is a lab instrument guide, not marketing material.
- **Procedures**: Use numbered lists for step-by-step workflows. Use bullet lists for feature descriptions.
- **GUI references**: Use **bold** for menu items, button labels, and dialog titles (e.g., "click **START**", "open **Tools → Raw Data View**").
- **Keyboard shortcuts**: Format as `Ctrl+O` (Windows/Linux) / `Cmd+O` (macOS).
- **Physics**: Explain QCM concepts briefly where they help the user understand what the software is showing, but keep the focus on the software. Link to external references for deeper theory.
- **Values and units**: Always include units. Use Hz, kHz, MHz for frequency; ×10⁻⁶ for dissipation; °C for temperature; ms for sampling time.
- **Tips and warnings**: Use blockquote format:
  - `> **Tip:** ...` for helpful suggestions
  - `> **Note:** ...` for important information
  - `> **Warning:** ...` for things that can cause data loss or confusion
- **Cross-references**: Link between chapters (e.g., "see [Chapter 10: Auto-Tracking](#10-auto-tracking)").
- **Do NOT include**: Source code internals, implementation details (e.g., class names, queue numbers, ring buffer sizes), or developer-facing information. This is an end-user guide.
- **Do NOT invent features**: Only describe what is documented in the brief and this supplementary file. If unsure, omit rather than guess.
- **Image placeholders**: Every procedure that involves a GUI interaction should have at least one image placeholder nearby. Aim for 15–25 placeholders total across the document. Group related screenshots (e.g., before/after of a reference set) when it makes sense.

---

## 9. Practical examples to include

Weave these real-world scenarios into the relevant chapters:

- **Protein adsorption monitoring**: Connect → Peak Detection → select F0 → Set Reference → add protein solution → watch Δf decrease as mass binds → compare Δf across overtones for rigidity assessment
- **Sensor quality check**: Run Peak Detection → open Peak Data View → verify all expected overtones are detected → if F7 or F9 are missing, this is normal for heavily loaded sensors
- **Long experiment**: Enable CSV export → START → let it run for hours → use Log Data View afterwards to replay and analyze with cursors → export cursor-selected statistics
- **Recovering from "Tracking Stopped"**: Understand the red warning → check sensor connection → if sensor is fine, wait for auto-resume (5 good sweeps) → if not, STOP and re-run Peak Detection

---

## 10. What NOT to include from the brief

These sections are for developer reference only — do not reproduce in the user guide:

- §18 (Version History Reference) — link to CHANGELOG.md instead
- §19 (Screenshots Needed) — this was an internal planning list
- Internal parameter names (e.g., `_err1`, `_err2`, `trim_mean_fraction`, `SG_window_size`)
- Line numbers or file paths from the source code
- The `tools/qcm_data_analyzer.py` script (it is a developer tool, not shipped in the release bundle)

---

*End of supplementary prompt. Feed this file together with USER_GUIDE_BRIEF.md to the AI.*
