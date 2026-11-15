@echo off
rem Uygulamayi paketler:  dist\CanliTurkceAltyazi\CanliTurkceAltyazi.exe
rem Gerekenler:  py -m pip install pyinstaller PySide6 numpy requests ^
rem              winrt-runtime winrt-Windows.Media.Ocr winrt-Windows.Globalization ^
rem              winrt-Windows.Graphics.Imaging winrt-Windows.Storage.Streams ^
rem              winrt-Windows.Foundation winrt-Windows.Foundation.Collections
cd /d "%~dp0"
py -m PyInstaller --noconfirm --clean --windowed --onedir ^
  --name CanliTurkceAltyazi --icon "%~dp0simge.ico" ^
  --distpath dist --workpath build --specpath build ^
  --collect-submodules winrt ^
  --hidden-import winrt.windows.media.ocr ^
  --hidden-import winrt.windows.globalization ^
  --hidden-import winrt.windows.graphics.imaging ^
  --hidden-import winrt.windows.storage.streams ^
  --hidden-import winrt.windows.foundation ^
  --hidden-import winrt.windows.foundation.collections ^
  --exclude-module cv2 --exclude-module onnxruntime ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets ^
  --exclude-module PySide6.QtPdf --exclude-module PySide6.QtQml ^
  --exclude-module PySide6.QtQuick --exclude-module tkinter ^
  canli_ceviri.py
if errorlevel 1 exit /b 1
copy /y BENIOKU.txt dist\CanliTurkceAltyazi\ >nul
echo.
echo Paket hazir: dist\CanliTurkceAltyazi
echo Kurulum dosyasi icin:  ISCC.exe kurulum.iss
