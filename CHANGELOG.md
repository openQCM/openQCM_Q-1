# openQCM Q-1 - Changelog v3.0

## Version 3.0 - February 2026

---

# PART 1: CODE FIXES AND OPTIMIZATIONS

## CRITICAL FIX: Signal Accumulation (Memory Leak)

### Problem
In `_update_plot()`, `sigResized.connect()` was called on every timer tick (50ms), causing exponential accumulation of signal handlers.

```python
# BEFORE - in _update_plot() called every 50ms
def updateViews1():
    self._plt1.setGeometry(self._plt0.vb.sceneBoundingRect())
    self._plt1.linkedViewChanged(self._plt0.vb, self._plt1.XAxis)

updateViews1()
self._plt0.vb.sigResized.connect(updateViews1)  # MEMORY LEAK
```

### Impact
| Time | Accumulated Handlers | Effect |
|------|---------------------|--------|
| 1 sec | 20 handlers | Slight slowdown |
| 10 sec | 200 handlers | Laggy GUI |
| 1 min | 1200 handlers | Resize impossible |

### Solution
Moved `sigResized.connect()` to `_configure_plot()` (called once at startup).

```python
# AFTER - in _configure_plot() called ONCE
def updateViews1():
    self._plt1.setGeometry(self._plt0.vb.sceneBoundingRect())
    self._plt1.linkedViewChanged(self._plt0.vb, self._plt1.XAxis)

self._plt0.vb.sigResized.connect(updateViews1)  # Single handler
updateViews1()  # Initial sync
```

### Modified Files
- `mainWindow.py`: lines 488-530 (`_configure_plot`)
- `mainWindow.py`: lines 805-827 (`_update_plot` - REFERENCE SET section)
- `mainWindow.py`: lines 844-870 (`_update_plot` - REFERENCE NOT SET section)

---

## OPTIMIZATION: CPU with setData()

### Problem
Inefficient `clear()` + `plot()` pattern on every timer tick.

### Solution
Use persistent `PlotCurveItem` objects with `setData()`.

```python
# Initialization (once)
self._curve_frequency = self._plt2.plot(pen=Constants.plot_colors[2], name='Frequency')

# Update (every 50ms)
self._curve_frequency.setData(x=time_buffer, y=freq_buffer)
```

### Benefits
- Eliminates continuous memory allocation/deallocation
- Reduces CPU overhead
- Smoother plot rendering

---

## OPTIMIZATION: Resize Event Debouncing

### Problem
During window resize, plots were redrawn continuously causing lag.

### Solution
Implemented debounce mechanism that suspends updates during resize.

```python
def resizeEvent(self, event):
    if hasattr(self, '_resize_timer'):
        self._is_resizing = True
        self._resize_timer.start(150)  # 150ms debounce
    super(MainWindow, self).resizeEvent(event)

def _on_resize_finished(self):
    self._is_resizing = False

def _update_plot(self):
    # Always consume queues (prevents overflow)
    self.worker.consume_queue1()
    # ...

    # Skip drawing during resize
    if self._is_resizing:
        return
```

---

## CONFIG: Timer Polling

Timer reduced from 200ms to 50ms for better responsiveness.

```python
# constants.py
plot_update_ms = 50  # Was 200ms
```

---

# PART 2: GUI DEVELOPMENT

## Unified Single Window Interface

Consolidated original 3-window architecture into single unified window.

### Layout
```
┌─────────────────────────────────────────────────────────────┐
│                        Menu Bar                             │
├──────────┬────────────────────────────────┬─────────────────┤
│          │                                │                 │
│  LEFT    │          CENTER                │     RIGHT       │
│ SIDEBAR  │         (TabWidget)            │    SIDEBAR      │
│          │                                │                 │
│ Controls │  ┌──────────┬───────────┐      │  Current        │
│          │  │  Plots   │ System Log│      │  Readings       │
│ - Mode   │  ├──────────┴───────────┤      │                 │
│ - Port   │  │                      │      │  Reference      │
│ - Freq   │  │   Amplitude/Phase    │      │                 │
│          │  │                      │      │  Software       │
│ Actions  │  │   Frequency/Diss     │      │  Info           │
│          │  │                      │      │                 │
│ Plot     │  │   Temperature        │      │                 │
│ Controls │  │                      │      │                 │
│          │  └──────────────────────┘      │                 │
│ Status   │                                │                 │
└──────────┴────────────────────────────────┴─────────────────┘
```

---

## Tab System

### TAB 1: Plots
Real-time graphs:
- Amplitude / Phase (dual Y-axis)
- Resonance Frequency / Dissipation (dual Y-axis)
- Temperature

### TAB 2: System Log
Integrated console displaying all log messages:
- Redirects `stdout` and `stderr`
- Auto timestamp `[HH:MM:SS]`
- Monospace font (Consolas)
- Dark background with green text (#00ff00)

```python
class LogStream:
    def write(self, text):
        timestamp = datetime.now().strftime("[%H:%M:%S] ")
        QtCore.QMetaObject.invokeMethod(
            self.text_widget, "append",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, timestamp + text.rstrip())
        )
```

---

## Dark/Light Theme System

### Menu Access
`View > Theme > Dark Theme / Light Theme`

### Dark Theme Colors
| Element | Color |
|---------|-------|
| Background | #2b2b2b |
| Foreground | #e0e0e0 |
| Accent | #00bcd4 |
| Plot BG | #2b2b2b |

### Light Theme Colors
| Element | Color |
|---------|-------|
| Background | #f5f5f5 |
| Foreground | #333333 |
| Accent | #00838f |
| Plot BG | #ffffff |

### Curve Colors (Light Theme)
Darker colors for visibility on white background:
- Frequency: #0066cc
- Dissipation: #cc6600
- Temperature: #cc3300

---

## Layout Fixes

### Minimum Window Height
```python
MainWindow.setMinimumSize(QtCore.QSize(1200, 720))
```

### Plot Control Buttons
Fixed height to prevent overlap:
```python
self.pButton_Clear.setFixedHeight(30)
self.pButton_Reference.setFixedHeight(30)
self.pButton_Autoscale.setFixedHeight(30)
```

---

## Plot Enhancements

### Grid
Added grid with transparency on all plots:
```python
self._plt0.showGrid(x=True, y=True, alpha=0.3)
```

### Legends
Added legends to identify curves:
```python
self._legend0 = self._plt0.addLegend(offset=(10, 10))
self._legend0.setBrush(pg.mkBrush('#3c3c3c80'))
```

### Standardized Axes
Uniform color (#a0a0a0) for all axes.

---

## Modified Files Summary

| File | Changes |
|------|---------|
| `mainWindow.py` | Signal fix, resize debounce, tab system, theme switch, log redirect |
| `mainWindow_ui.py` | TabWidget, SystemLog, dark/light stylesheets, layout fixes |
| `constants.py` | Timer 50ms |

---

*Development assisted by Claude Code - February 2025*
