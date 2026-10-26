@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto run
set "IDRADAR_PY="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul
if not errorlevel 1 set "IDRADAR_PY=py -3"
if defined IDRADAR_PY goto create
python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul
if not errorlevel 1 set "IDRADAR_PY=python"
if not defined IDRADAR_PY goto missing
:create
%IDRADAR_PY% -m venv .venv
if errorlevel 1 goto failed
type nul > ".venv\.idradar-installing"
:run
".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul
if errorlevel 1 goto missing
if not exist ".venv\.idradar-installing" goto launch
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "from pathlib import Path; Path('.venv/.idradar-installing').unlink(missing_ok=True)"
if errorlevel 1 goto failed
:launch
".venv\Scripts\python.exe" -m idradar %*
if errorlevel 1 goto failed
exit /b 0
:missing
echo 需要 Python 3.11 或更新版本，请从 https://www.python.org/downloads/ 安装并启用 PATH。
echo Python 3.11+ is required. Install it from https://www.python.org/downloads/ and enable PATH.
pause
exit /b 1
:failed
echo 启动失败，请检查上方错误、网络和 Python 环境。
echo Startup failed. Check the error above, your connection and Python environment.
pause
exit /b 1
