# Contributing to openQCM Q-1

Thank you for your interest in contributing to the openQCM Q-1 project.
This document explains how to set up a development environment, the
conventions we follow, and how to submit changes.

---

## Getting Started

### 1. Clone and set up the environment

```bash
git clone https://github.com/openQCM/openQCM_Q-1.git
cd openQCM_Q-1
chmod +x setup_env.sh
./setup_env.sh
```

This creates a `openqcm` conda environment with all pinned dependencies.
Alternatively:

```bash
conda env create -f environment.yml
```

### 2. Run the application

```bash
conda activate openqcm
python run.py
```

### 3. Verify syntax before committing

```bash
python -c "import ast; ast.parse(open('openQCM/ui/mainWindow.py').read()); print('OK')"
```

Run this on every file you modify — it catches syntax errors before they
reach the repository.

---

## Code Conventions

- **Language**: all source code, comments, docstrings, and commit messages
  in **English**. Comments should explain *why*, not restate *what*.
- **Style**: follow PEP 8 for imports (stdlib, third-party, project) and
  naming. The codebase uses `snake_case` for functions/variables and
  `PascalCase` for classes.
- **Paths**: always use `os.path.join()` for file paths.
  Use `get_data_path()` (from `openQCM/common/resources.py`) for writable
  paths and `get_resource_path()` for read-only bundled assets.
- **Qt signals**: never connect signals inside a timer callback — connect
  once during initialization.
- **Right-click menus**: if you add a context menu entry, update *every*
  custom handler (see the list in `CLAUDE.md` §9).

---

## Project Layout

```
openQCM/
├── core/          # constants, ring buffer, worker (GUI ↔ child process bridge)
├── processors/    # Serial, Calibration, Parser (multiprocessing children)
├── ui/            # mainWindow, mainWindow_ui, calibrationPlot, popUp
└── common/        # utilities: logging, file I/O, OS detection, resources
```

The application uses a **multiprocessing pipeline**: child processes
(`SerialProcess`, `CalibrationProcess`) handle serial I/O and signal
processing, communicating with the GUI through shared queues. Child
processes never touch Qt directly.

See `CLAUDE.md` for the full architecture description and gotchas.

---

## Submitting Changes

1. **Fork** the repository and create a feature branch from `main`.
2. Make your changes in small, focused commits.
3. Write a clear commit message: short title (under 70 chars), blank line,
   then a body explaining *why* the change is needed.
4. Run the syntax check (`ast.parse`) on all modified files.
5. Test on at least one platform (macOS, Windows, or Linux) with a real
   openQCM Q-1 device if possible.
6. Open a **Pull Request** against `main` with a description of what your
   change does and how you tested it.

---

## What to Avoid

- Do not commit `.DS_Store`, `dist/`, `build/`, `__pycache__/`, or
  runtime-generated files (`logged_data/*.csv`, `*.log`).
- Do not add heavy dependencies (`pandas`, `matplotlib`, `tkinter`) to the
  main application — the PyInstaller bundle is kept under 350 MB.
- Do not change `_err1` / `_err2` semantics without understanding the
  tracking-safety hysteresis state machine (documented in `CLAUDE.md` §5).
- Do not move resource path resolution off `get_data_path` /
  `get_resource_path` — both dev and frozen modes depend on them.

---

## Reporting Issues

Open an issue on [GitHub](https://github.com/openQCM/openQCM_Q-1/issues)
with:

- Your OS and Python version
- Steps to reproduce the problem
- Console output or screenshots if applicable
- The firmware version shown in **Help → Check Firmware Version**

---

## License

By contributing, you agree that your contributions will be licensed under
the [GNU General Public License v3.0](LICENSE), the same license as the
rest of the project.

---

## Contact

- **Website**: [openqcm.com](https://openqcm.com/)
- **Email**: info@openqcm.com
- **GitHub**: [github.com/openQCM](https://github.com/openQCM)
