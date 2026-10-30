# Apple Silicon development setup — plan (not done yet)

Status: **planned, approved 2026-10-30, not started.** Everything below is run
from the Terminal, one step at a time.

## Why

The development Mac is now an Apple M5 Pro (arm64, macOS 27). The Anaconda
migrated from the Intel iMac (`~/opt/anaconda3`) is an x86_64 build and fails
with `bad CPU type in executable` because Rosetta 2 is not installed.

Two constraints drive the plan:

- `environment.yml` pins **PyQt 5.9.2 / Qt 5.9.7**, which have no arm64 build.
  The earliest PyQt available for Apple Silicon is 5.15. On the M2 MacBook Air
  (validated 2026-06-24) the app therefore ran with x86_64 packages under
  Rosetta, via `setup_env.sh` (`CONDA_SUBDIR=osx-64`).
- Apple keeps full Rosetta 2 only through macOS 27. From macOS 28 it remains
  for a limited set of legacy games and frameworks, so an x86_64 environment is
  a bridge, not a long-term setup.

## Plan

One **native arm64 Miniconda** as the only conda on the machine, holding two
environments:

| Environment | Architecture | Purpose |
|---|---|---|
| `openqcm-x86-64` | x86_64 under Rosetta | the verified pinned stack — day-to-day work now |
| `openqcm-arm64` | native arm64 | new stack designed for Apple Silicon — future main env |

Miniconda (not Miniforge) keeps the `defaults` channel that `environment.yml`
uses, so the pinned versions resolve exactly as on the other machines. An
arm64 conda can create x86_64 environments; `setup_env.sh` relies on this.

The old `~/opt/anaconda3` stays in place for now (it also holds other
projects' envs, usable once Rosetta is installed). Remove it only after the
new setup is proven.

### 1 · Install Rosetta 2 (needs the admin password)

```bash
softwareupdate --install-rosetta --agree-to-license
```

### 2 · Install Miniconda arm64

```bash
curl -fsSLo ~/Downloads/Miniconda3-latest-MacOSX-arm64.sh https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh
```

```bash
bash ~/Downloads/Miniconda3-latest-MacOSX-arm64.sh -b -p ~/miniconda3
```

```bash
~/miniconda3/bin/conda init zsh
```

`conda init` replaces the old Anaconda block in `~/.zshrc`. Open a new
Terminal tab, then check that conda itself is native:

```bash
conda info | grep platform
```

Expected: `platform : osx-arm64`. Recent Miniconda releases ask to accept the
Anaconda terms of service for the `defaults` channels the first time; follow
the `conda tos accept ...` command it prints.

### 3 · Create `openqcm-x86-64` (pinned stack, under Rosetta)

```bash
CONDA_SUBDIR=osx-64 conda create -n openqcm-x86-64 python=3.9.12 -y
```

```bash
conda activate openqcm-x86-64
```

```bash
conda config --env --set subdir osx-64
```

```bash
conda install pyqt=5.9.2 qt=5.9.7 sip=4.19.13 pyqtgraph=0.11.0 numpy=1.21.5 scipy=1.7.3 pyserial=3.5 pandas=1.4.2 lxml -y
```

```bash
pip install progressbar==2.5
```

Check the architecture and the versions:

```bash
python -c "import platform, numpy, scipy; from PyQt5.QtCore import PYQT_VERSION_STR; print(platform.machine(), numpy.__version__, scipy.__version__, PYQT_VERSION_STR)"
```

Expected: `x86_64 1.21.5 1.7.3 5.9.2`. Then run the GUI from `OPENQCM/` with
`python run.py` and test it with an instrument connected.

`setup_env.sh` does the same but hard-codes the env name `openqcm`; the manual
commands above are used to get the `openqcm-x86-64` name without editing it.

### 4 · Create `openqcm-arm64` (later, on its own branch)

Native stack, versions to be settled when the work starts:

- Python 3.11 or 3.12, PyQt 5.15, recent pyqtgraph (0.13.x), numpy, scipy,
  pyserial, pandas, lxml.
- Work on a dedicated branch (e.g. `feature/apple-silicon-native`):
  pyqtgraph 0.11 → 0.13 has API changes that will need code fixes.
- Validate with an instrument connected: plots, right-click menus, dialogs,
  Peak Detection, measurement, serial reconnect, firmware check.
- When it passes, update `environment.yml`, `requirements.txt`,
  `setup_env.sh` and the Apple Silicon note in `README.md` (which today says
  Rosetta is required).
- The Windows build (PyInstaller, built on Windows) does not depend on this;
  decide separately whether to move it to the new stack too.

Once `openqcm-arm64` is the main environment, `openqcm-x86-64` can be deleted
whenever Rosetta is no longer available.
