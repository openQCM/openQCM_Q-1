"""
Package the Markdown edition of the user manual for distribution.

Run from the repository root:

    python docs/tools/build_manual_zip.py

Writes docs/user-manual/openQCM_Q-1_Manual_Markdown_Source.zip with the .md,
every image it links (annotated screenshots, schematics with their SVG
sources, icon) and a README.txt. The ZIP is a release attachment and is
git-ignored. The unannotated captures in assets/gui/raw/ are not included.
"""
import os
import re
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANUAL_DIR = os.path.join(REPO_ROOT, 'docs', 'user-manual')
BASENAME = 'openQCM_Q-1_Software_User_Manual_v3.0'
ZIP_PATH = os.path.join(MANUAL_DIR, 'openQCM_Q-1_Manual_Markdown_Source.zip')
ROOT = 'openQCM_Q-1_manual_source/'

README = """openQCM Q-1 Software User Manual
Edition {edition}, {date}

CONTENTS
- {md}: the complete English manual, with the same text, tables, captions and references as the Word/PDF edition.
- assets/: the {n_png} PNG images linked by the manual: {n_gui} annotated screenshots in assets/gui/, the schematics and the openQCM icon. Editable SVG sources of the schematics are included.

READING AND AI USE
Extract the entire ZIP before opening the Markdown. Keep the assets folder beside the .md file; every image uses a portable relative link and descriptive alt text, and each figure caption also appears as visible text. Numbered callouts in the screenshots are listed in their captions.

For another AI, supply the complete extracted folder if supported, otherwise the .md with all PNG files. Text and alt text do not replace inspecting the images.

The Markdown has no fixed pagination; use the contents links to navigate. Page numbers exist only in the Word/PDF edition.

FIGURE PROVENANCE
The schematics are original logical diagrams based on the cited source documentation and code; they are not wiring drawings. The screenshots show release {release}, captured on macOS with the scripts in the repository's docs/tools folder, partly with a connected Q-1 and partly from saved files. No measurement data were fabricated.
"""


def main():
    md = open(os.path.join(MANUAL_DIR, BASENAME + '.md'), encoding='utf-8').read()
    edition, date = re.search(r'Edition ([\d.]+)\n(.+)', md).groups()
    release = re.search(r'Source baseline (\S+)', md).group(1)
    images = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', md) + re.findall(r'<img src="([^"]+)"', md)
    svgs = [p[:-4] + '.svg' for p in images
            if os.path.exists(os.path.join(MANUAL_DIR, p[:-4] + '.svg'))]

    readme = README.format(edition=edition, date=date.strip(), md=BASENAME + '.md',
                           n_png=len(images), n_gui=sum('/gui/' in p for p in images),
                           release=release)
    with zipfile.ZipFile(ZIP_PATH, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(MANUAL_DIR, BASENAME + '.md'), ROOT + BASENAME + '.md')
        z.writestr(ROOT + 'README.txt', readme)
        for rel in sorted(set(images + svgs)):
            z.write(os.path.join(MANUAL_DIR, rel), ROOT + rel)
    print('wrote {} ({} images, {} SVG)'.format(
        os.path.relpath(ZIP_PATH, REPO_ROOT), len(images), len(svgs)))


if __name__ == '__main__':
    main()
