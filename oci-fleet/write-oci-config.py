#!/usr/bin/env python3
"""
Paste the OCI config snippet from the console into this script.
Run:  python oci-fleet/write-oci-config.py

It will write ~/.oci/config with the correct key_file path for Windows.
"""
import pathlib, re, sys, textwrap

KEY_FILE = str(pathlib.Path.home() / '.oci' / 'oci_api_key.pem')
CONFIG   = pathlib.Path.home() / '.oci' / 'config'

print("Paste the config snippet from OCI Console (ends with key_file=...).")
print("Press Enter twice when done:\n")

lines = []
blank = 0
while blank < 2:
    try:
        line = input()
    except EOFError:
        break
    if line.strip() == '':
        blank += 1
    else:
        blank = 0
    lines.append(line)

snippet = '\n'.join(lines).strip()
if not snippet:
    print("Nothing pasted. Exiting.")
    sys.exit(1)

# Always set key_file to our generated key regardless of what OCI suggested
snippet = re.sub(r'key_file\s*=.*', f'key_file={KEY_FILE}', snippet)

# Ensure [DEFAULT] header
if not snippet.startswith('['):
    snippet = '[DEFAULT]\n' + snippet

CONFIG.write_text(snippet + '\n', encoding='utf-8')
print(f"\nWritten: {CONFIG}")
print("\nContents:")
print(CONFIG.read_text())
print("\nNow run:  python oci-fleet/oci-setup-wizard.py")
