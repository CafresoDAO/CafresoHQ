@echo off
:: CafresoAI -- quick launcher
:: For HTTPS (required for iOS service worker + full PWA):
::   1. Run once:  winget install FiloSottile.mkcert
::                 mkcert -install
::                 mkcert YOUR_LAN_IP localhost 127.0.0.1
::      (replace YOUR_LAN_IP with e.g. 192.168.1.42)
::   2. Set the env vars below to the generated .pem files, then re-run.
::      The cert file is named like: 192.168.1.42+2.pem
::                        key file: 192.168.1.42+2-key.pem
::
:: Leave blank to run plain HTTP (still works on same-network or via Twingate).

set OPENCLAW_TLS_CERT=
set OPENCLAW_TLS_KEY=

cd /d "%~dp0"
python serve.py
pause
