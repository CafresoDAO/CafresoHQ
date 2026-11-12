#!/usr/bin/env python3
"""No view brings its own React.

The UI runs on the React the page loads. views/canisters.jsx imported 'react'
from npm instead, which bundled a second copy whose hooks have no renderer:
clicking Canisters in the rail crashed the whole office with "Cannot read
properties of null (reading 'useState')". Any module doing this again breaks
the same way, so the rule is checked for every UI source file.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
files = [p for pat in ('*.jsx', 'app/*.jsx', 'views/*.jsx', 'ui/*.jsx', 'modals/*.jsx') for p in ROOT.glob(pat)]
bad = [str(p.relative_to(ROOT)) for p in files
       if re.search(r'''^\s*import\b[^;]*\bfrom\s+['"]react(-dom)?['"]''', p.read_text(encoding='utf-8'), re.M)]
print(f'    checked {len(files)} files')
if bad:
    print('    FAIL  these import their own React: ' + ', '.join(bad))
    sys.exit(1)
print('    ok    no UI file imports its own React')
