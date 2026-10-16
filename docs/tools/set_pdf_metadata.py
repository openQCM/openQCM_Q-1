"""
Write title, author, subject and keywords into the user-manual PDF.

Word for Mac exports the PDF through macOS Quartz, which leaves the
document information dictionary almost empty, so PDF viewers show only the
file name. This appends an incremental update that replaces the /Info
object. The page content is untouched and no third-party package is
needed.

    python docs/tools/set_pdf_metadata.py           # called by export_manual_pdf.sh
"""
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANUAL_DIR = os.path.join(REPO_ROOT, 'docs', 'user-manual')
BASENAME = 'openQCM_Q-1_Software_User_Manual_v3.0'
PDF_PATH = os.path.join(MANUAL_DIR, BASENAME + '.pdf')
MD_PATH = os.path.join(MANUAL_DIR, BASENAME + '.md')
# A literal PDF string, allowing backslash-escaped parentheses inside.
PDF_STRING = r'\((?:\\.|[^\\)])*\)'


def pdf_text(s):
    """Encode a string as a PDF text string (UTF-16BE hex when not ASCII)."""
    if all(32 <= ord(c) < 127 for c in s):
        return '(' + s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)') + ')'
    return '<FEFF' + s.encode('utf-16-be').hex().upper() + '>'


def main():
    md = open(MD_PATH, encoding='utf-8').read()
    edition, date = re.search(r'Edition ([\d.]+)\n(.+)', md).groups()
    release = re.search(r'Source baseline (\S+)', md).group(1)

    data = open(PDF_PATH, 'rb').read()
    tail = data[data.rindex(b'trailer'):].decode('latin-1')
    startxref = int(re.search(r'startxref\s+(\d+)', tail).group(1))
    size = int(re.search(r'/Size (\d+)', tail).group(1))
    root = re.search(r'/Root (\d+ \d+ R)', tail).group(1)
    info_num = int(re.search(r'/Info (\d+) 0 R', tail).group(1))
    ids = re.search(r'/ID\s*\[\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', tail)

    old = re.search(rb'\n%d 0 obj\s*(<<.*?>>)\s*endobj' % info_num, data, re.S).group(1).decode('latin-1')
    keep = ''.join(m.group(0) for m in re.finditer(r'/(Producer|CreationDate)\s*' + PDF_STRING, old))

    info = ('<<%s/ModDate(%s)/Title%s/Author%s/Subject%s/Keywords%s>>' % (
        keep,
        re.search(r'/CreationDate\s*\(((?:\\.|[^\\)])*)\)', old).group(1) if 'CreationDate' in old else '',
        pdf_text('openQCM Q-1 Software User Manual v3.0'),
        pdf_text('openQCM / Novaetech S.r.l.'),
        pdf_text('Software user manual for openQCM Q-1 %s — Edition %s, %s' % (release, edition, date)),
        pdf_text('openQCM, Q-1, QCM-D, quartz crystal microbalance, user manual, %s' % release),
    ))

    body = '\n%d 0 obj\n%s\nendobj\n' % (info_num, info)
    offset = len(data) + 1
    xref_at = len(data) + len(body)
    update = body + 'xref\n%d 1\n%010d 00000 n \ntrailer\n<</Size %d/Root %s/Info %d 0 R%s/Prev %d>>\nstartxref\n%d\n%%%%EOF\n' % (
        info_num, offset, size, root, info_num,
        '/ID[<%s><%s>]' % (ids.group(1), ids.group(2)) if ids else '',
        startxref, xref_at)
    with open(PDF_PATH, 'ab') as f:
        f.write(update.encode('latin-1'))
    print('metadata written to', os.path.relpath(PDF_PATH, REPO_ROOT))


if __name__ == '__main__':
    main()
