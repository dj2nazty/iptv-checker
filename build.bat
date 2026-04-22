@echo off
title IPTV Stream Checker — Build Script
color 0A
echo.
echo ============================================================
echo   IPTV Stream Checker v2.0.0 — Build Script
echo ============================================================
echo.

set PYTHON=C:\Users\Dj2nazty\AppData\Local\Programs\Python\Python39\python.exe
set PYINSTALLER=C:\Users\Dj2nazty\AppData\Local\Programs\Python\Python39\Scripts\pyinstaller.exe
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
set ROOT=%~dp0

cd /d "%ROOT%"

echo [1/4] Cleaning old build output...
if exist dist\IPTVChecker rmdir /s /q dist\IPTVChecker
if exist build rmdir /s /q build
echo     Done.
echo.

echo [2/4] Building EXE with PyInstaller...
"%PYINSTALLER%" IPTVChecker.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed!
    pause
    exit /b 1
)
echo     EXE built successfully.
echo.

echo [3/4] Compiling Windows Installer with Inno Setup...
%ISCC% installer.iss
if errorlevel 1 (
    echo.
    echo ERROR: Inno Setup compile failed!
    pause
    exit /b 1
)
echo     Installer compiled successfully.
echo.

echo [4/4] Done!
echo.
echo ============================================================
echo   Output: dist\Setup_IPTVChecker_v2.0.0.exe
echo ============================================================
echo.
echo   The installer:
echo    - Installs to Program Files\IPTV Stream Checker
echo    - Creates Start Menu shortcut
echo    - Optional Desktop shortcut
echo    - Registers in Add/Remove Programs with uninstall
echo    - Automatically upgrades over older versions
echo.
explorer dist
pause
