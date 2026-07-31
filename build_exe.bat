@echo off
REM build_exe.bat - construit OpenTraderPro.exe sur Windows.

echo ============================================
echo   OpenTrader Pro - build de l'executable
echo ============================================

where python >nul 2>nul
if errorlevel 1 (
    echo [ERREUR] Python introuvable dans le PATH. Installez Python 3.13.
    exit /b 1
)

if not exist venv (
    echo [1/4] Creation de l'environnement virtuel...
    python -m venv venv
)

echo [2/4] Activation du venv et installation des dependances...
call venv\Scripts\activate.bat
pip install --upgrade pip >nul
pip install -r requirements.txt
pip install pyinstaller

echo [3/4] Compilation avec PyInstaller...
pyinstaller packaging\OpenTraderPro.spec --noconfirm

echo [4/4] Termine.
echo.
echo L'executable se trouve dans : dist\OpenTraderPro\OpenTraderPro.exe
echo.
pause
