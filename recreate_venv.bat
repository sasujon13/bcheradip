@echo off
REM Recreate venv with current default Python and install requirements
echo Recreating venv...
if exist venv rmdir /s /q venv
python -m venv venv
call venv\Scripts\activate.bat
pip install -r requirements.txt
echo.
echo Done. Activate with: venv\Scripts\activate
echo Then run: python manage.py runserver
pause
