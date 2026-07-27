@echo off
echo Building FCC000 Collector executable...
echo.

REM Check if PyInstaller is installed
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
)

REM Run the build script
python build_exe.py

echo.
echo Build process complete!
echo The executable can be found in the 'dist' folder.
pause

