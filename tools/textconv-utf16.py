"""Git textconv for @Resources/Calendar.lua (UTF-16 LE with BOM) so diffs are readable.

Enable once per clone:
    git config diff.utf16.textconv "python tools/textconv-utf16.py"
"""
import sys

data = open(sys.argv[1], 'rb').read()
if data[:2] == b'\xff\xfe':
    text = data[2:].decode('utf-16-le')
else:
    text = data.decode('utf-8', 'replace')  # versions committed before the switch to UTF-16
sys.stdout.buffer.write(text.replace('\r\n', '\n').encode('utf-8'))
