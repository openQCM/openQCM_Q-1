#!/bin/sh
# Export the user manual .docx to PDF with Microsoft Word for Mac.
#
# Run from the repository root after build_manual_docx.py:
#
#     sh docs/tools/export_manual_pdf.sh
#
# Word first updates every field, so the contents-page PAGEREF numbers
# match the final pagination, then saves the .docx and exports the PDF
# next to it. Word may ask once for permission to access the folder.
# Finally set_pdf_metadata.py fills in title, author, subject and keywords.
set -e
DIR="$(cd "$(dirname "$0")/../user-manual" && pwd)"
BASE="openQCM_Q-1_Software_User_Manual_v3.0"
DOCX="$DIR/$BASE.docx"
PDF="$DIR/$BASE.pdf"

osascript <<EOF
tell application "Microsoft Word"
    open POSIX file "$DOCX"
    set d to active document
    set n to count of fields of d
    repeat with i from 1 to n
        update field (field i of d)
    end repeat
    save d
    save as d file name "$PDF" file format format PDF
    close d saving no
end tell
EOF
echo "wrote $PDF"
python "$(dirname "$0")/set_pdf_metadata.py"
