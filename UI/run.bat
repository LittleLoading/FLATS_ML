@echo off

echo Installing requirements...
python -m pip install -r ..\requirements.txt

echo.
echo Starting app...
python app.py

pause