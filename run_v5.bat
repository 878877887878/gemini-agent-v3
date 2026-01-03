@echo off
call venv\Scripts\activate
pip install -r requirements_v5.txt
python main_v5.py
pause