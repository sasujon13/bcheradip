@echo off
REM Quick start script for local XAMPP development
REM Run this file to start the Django development server

echo ========================================
echo   Cheradip Backend - Local Development
echo ========================================
echo.

REM Check if .env file exists
if not exist .env (
    echo [WARNING] .env file not found!
    echo.
    echo Creating .env file from template...
    call create_env_file.bat
    echo.
)

REM Check if database exists (basic check)
echo Checking database connection...
python manage.py check --database default
if errorlevel 1 (
    echo.
    echo [ERROR] Database connection failed!
    echo Please check:
    echo   1. XAMPP MySQL service is running
    echo   2. Database 'cheradip_cheradip' exists in phpMyAdmin
    echo   3. .env file has correct database credentials
    echo.
    pause
    exit /b 1
)

echo.
echo [INFO] Database connection OK!
echo.

REM Check migrations
echo Checking migrations...
python manage.py showmigrations --list | findstr "\[ \]" > nul
if errorlevel 1 (
    echo [INFO] All migrations are applied.
) else (
    echo [WARNING] Some migrations are not applied!
    echo Running migrations...
    python manage.py migrate
    if errorlevel 1 (
        echo [ERROR] Migration failed!
        pause
        exit /b 1
    )
)

echo.
echo ========================================
echo   Starting Django Development Server
echo ========================================
echo.
echo Backend API: http://127.0.0.1:8000/api/
echo Admin Panel: http://127.0.0.1:8000/admin/
echo.
echo Press CTRL+C to stop the server
echo.
echo ========================================
echo.

python manage.py runserver

