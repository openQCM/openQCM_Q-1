"""
Annotate and resize the raw GUI captures for the openQCM Q-1 user manual.

Run from the repository root after capture_gui.py:

    python docs/tools/annotate_gui.py

Reads docs/user-manual/assets/gui/raw/*.png (unannotated, Retina pixel
ratio 2) and writes the published images to docs/user-manual/assets/gui/.
Annotations are numbered callouts (filled circles) and highlight boxes; the
matching legend lives in the figure caption of the manual, so the numbers
here must stay in sync with it.

All coordinates below are in raw-capture pixels. Every image is scaled by
the same factor, so GUI text has the same size in every figure and the full
main window ends up 1600 px wide.

When the GUI layout changes, re-run capture_gui.py, check the callout
positions against the new raw images and update the SPECS table.
"""
import os

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GUI_DIR = os.path.join(REPO_ROOT, 'docs', 'user-manual', 'assets', 'gui')
RAW_DIR = os.path.join(GUI_DIR, 'raw')

SCALE = 1600 / 2400          # full main window (2400 px raw) -> 1600 px
# Palette of the manual's schematics (qcm_signal_chain.svg), so callouts
# match Figure 1 instead of competing with the GUI's own colours.
INK = (0x24, 0x5D, 0x86)
CIRCLE_FILL = (0xF3, 0xF7, 0xFA)
BORDER = (187, 187, 187)
CIRCLE_R = 24
CIRCLE_EDGE_W = 6
BOX_W = 5

_FONT_DIRS = ['/System/Library/Fonts/Supplemental', '/Library/Fonts',
              'C:\\Windows\\Fonts', '/usr/share/fonts/truetype/dejavu']


def _font(bold, size):
    names = (['Arial Bold.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf'] if bold
             else ['Arial.ttf', 'arial.ttf', 'DejaVuSans.ttf'])
    for d in _FONT_DIRS:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    return ImageFont.load_default()


NUM_FONT = _font(True, 30)
HEAD_FONT = _font(True, 30)


def load(name):
    return Image.open(os.path.join(RAW_DIR, name + '.png')).convert('RGB')


def pad(img, left=0, top=0, right=0, bottom=0, color=(255, 255, 255)):
    out = Image.new('RGB', (img.width + left + right, img.height + top + bottom), color)
    out.paste(img, (left, top))
    return out


def callout(draw, n, xy):
    x, y = xy
    draw.ellipse([x - CIRCLE_R, y - CIRCLE_R, x + CIRCLE_R, y + CIRCLE_R],
                 fill=CIRCLE_FILL, outline=INK, width=CIRCLE_EDGE_W)
    draw.text((x, y), str(n), font=NUM_FONT, fill=INK, anchor='mm')


def box(draw, rect):
    draw.rounded_rectangle(rect, radius=10, outline=INK, width=BOX_W)


def heading(draw, xy, text):
    draw.text(xy, text, font=HEAD_FONT, fill=(51, 51, 51))


def annotate(img, callouts=(), boxes=(), offset=(0, 0)):
    d = ImageDraw.Draw(img)
    ox, oy = offset
    for x1, y1, x2, y2 in boxes:
        box(d, (x1 + ox, y1 + oy, x2 + ox, y2 + oy))
    for n, (x, y) in callouts:
        callout(d, n, (x + ox, y + oy))
    return img


def finish(img, name):
    img = img.resize((round(img.width * SCALE), round(img.height * SCALE)), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, img.width - 1, img.height - 1], outline=BORDER, width=1)
    path = os.path.join(GUI_DIR, name + '.png')
    img.save(path, 'PNG', optimize=True)
    print('wrote {} ({}x{})'.format(os.path.relpath(path, REPO_ROOT), img.width, img.height))


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def fig_main_window():
    img = load('q1_06_main_window')
    boxes = [
        (22, 180, 456, 420),      # Serial Connection
        (22, 444, 456, 806),      # Measurement Setup
        (22, 828, 456, 1063),     # Current Readings
        (22, 1102, 456, 1360),    # Plot Controls
        (22, 1414, 456, 1660),    # Acquisition
        (1258, 53, 1620, 118),    # Plots / System Log tabs
        (540, 180, 1320, 564),    # Amplitude / Phase
        (1380, 180, 2352, 564),   # Temperature
        (540, 630, 2352, 1620),   # Resonance Frequency / Dissipation
        (532, 582, 2356, 601),    # splitter
        (4, 1740, 2396, 1796),    # status bar
    ]
    callouts = [
        (1, (420, 216)), (2, (420, 480)), (3, (420, 864)), (4, (420, 1138)),
        (5, (420, 1450)), (6, (1662, 86)), (7, (832, 201)), (8, (1808, 201)),
        (9, (1226, 654)), (10, (1446, 591)), (11, (800, 1768)),
    ]
    finish(annotate(img, callouts, boxes), 'q1_06_main_window')


def fig_serial_connection():
    img = pad(load('q1_04_serial_connection'), right=70, bottom=60)
    callouts = [(1, (473, 128)), (2, (108, 272)), (3, (323, 272))]
    finish(annotate(img, callouts), 'q1_04_serial_connection')


def fig_menus():
    names = [('File', 'q1_07_menu_file'), ('View', 'q1_07_menu_view'),
             ('View \u2192 Theme', 'q1_07_menu_view_theme'),
             ('Tools', 'q1_07_menu_tools'), ('Help', 'q1_07_menu_help')]
    ims = [(title, load(n)) for title, n in names]
    gap, head, margin = 40, 60, 30
    width = margin * 2 + sum(max(i.width, 200) for _, i in ims) + gap * (len(ims) - 1)
    height = margin * 2 + head + max(i.height for _, i in ims)
    out = Image.new('RGB', (width, height), (255, 255, 255))
    d = ImageDraw.Draw(out)
    x = margin
    for title, im in ims:
        heading(d, (x, margin), title)
        out.paste(im, (x, margin + head))
        x += max(im.width, 200) + gap
    finish(out, 'q1_07_menus')


def fig_mode_selection():
    left = pad(load('q1_08_mode_peak_detection'), right=70)
    right = pad(load('q1_08_mode_measurement'), right=70)
    annotate(left, [(1, (473, 128))])
    annotate(right, [(1, (473, 128)), (2, (473, 254)), (3, (473, 329))])
    gap, head, margin = 50, 60, 30
    out = Image.new('RGB', (margin * 2 + left.width + gap + right.width,
                            margin * 2 + head + max(left.height, right.height)),
                    (255, 255, 255))
    d = ImageDraw.Draw(out)
    heading(d, (margin, margin), 'Peak Detection mode')
    heading(d, (margin + left.width + gap, margin), 'Measurement mode')
    out.paste(left, (margin, margin + head))
    out.paste(right, (margin + left.width + gap, margin + head))
    finish(out, 'q1_08_mode_selection')


def fig_peak_data_view():
    img = load('q1_09_peak_data_view')
    callouts = [(1, (630, 33)), (2, (490, 283)), (3, (756, 315)), (4, (756, 1060))]
    finish(annotate(img, callouts), 'q1_09_peak_data_view')


def fig_context_menu():
    finish(load('q1_11_plot_context_menu'), 'q1_11_plot_context_menu')


def fig_live_plots():
    img = load('q1_12_live_plots')
    callouts = [
        (1, (68, 160)), (2, (800, 145)), (3, (590, 494)), (4, (905, 150)),
        (5, (1545, 494)), (6, (68, 605)), (7, (1810, 895)), (8, (1080, 1541)),
    ]
    finish(annotate(img, callouts), 'q1_12_live_plots')


def fig_measurement_parameters():
    finish(load('q1_13_measurement_parameters'), 'q1_13_measurement_parameters')


def fig_raw_data_view():
    img = load('q1_13_raw_data_view')
    callouts = [(1, (380, 34)), (2, (430, 236)), (3, (1596, 158)),
                (4, (1536, 630)), (5, (1890, 326)), (6, (1003, 814))]
    finish(annotate(img, callouts), 'q1_13_raw_data_view')


def fig_data_view():
    img = load('q1_14_data_view')
    callouts = [(1, (719, 34)), (2, (1995, 116)), (3, (1995, 819)), (4, (1234, 1445))]
    finish(annotate(img, callouts), 'q1_14_data_view')


def fig_cursors():
    img = load('q1_14_cursors')
    callouts = [(1, (669, 700)), (2, (1218, 700)), (3, (1545, 145)), (4, (180, 124))]
    finish(annotate(img, callouts), 'q1_14_cursors')


def fig_status_states():
    states = ['standby', 'peak_processing', 'peak_success', 'processing', 'monitoring']
    strips = [load('q1_15_status_' + s) for s in states]
    left, gap = 70, 14
    out = Image.new('RGB', (left + max(s.width for s in strips),
                            sum(s.height for s in strips) + gap * (len(strips) - 1)),
                    (255, 255, 255))
    d = ImageDraw.Draw(out)
    y = 0
    for n, s in enumerate(strips, 1):
        out.paste(s, (left, y))
        callout(d, n, (left // 2, y + s.height // 2))
        y += s.height + gap
    finish(out, 'q1_15_status_states')


FIGURES = [
    fig_serial_connection, fig_main_window, fig_menus, fig_mode_selection,
    fig_peak_data_view, fig_context_menu, fig_live_plots,
    fig_measurement_parameters, fig_raw_data_view, fig_data_view,
    fig_cursors, fig_status_states,
]


if __name__ == '__main__':
    for fig in FIGURES:
        fig()
