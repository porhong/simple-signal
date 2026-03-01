@echo off
REM Build SwiftEdge.exe. Requires: pip install -r requirements.txt -r requirements-build.txt
set PYTHONIOENCODING=utf-8
pyinstaller --noconfirm SwiftEdge.spec
echo.
echo Build done. Output: dist\SwiftEdge.exe
echo Place config.json in the same folder as SwiftEdge.exe (or pass path as first argument).
