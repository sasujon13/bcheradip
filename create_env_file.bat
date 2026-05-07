@echo off
REM Create .env file for XAMPP local development
REM Run this file in the bcheradip directory

echo Creating .env file for XAMPP local development...

(
echo # XAMPP Local Development Configuration
echo # Generated automatically
echo.
echo # Django Settings
echo SECRET_KEY=django-insecure-d37cp#^cs90*bzhh+pvvv$6+h$tm@crx6$=_*^=d^&g)k@+c%%rj
echo DEBUG=True
echo ALLOWED_HOSTS=localhost,127.0.0.1
echo.
echo # Database Configuration ^(XAMPP Default^)
echo DATABASE_NAME=cheradip_cheradip
echo DATABASE_USER=root
echo DATABASE_PASSWORD=
echo DATABASE_HOST=localhost
echo DATABASE_PORT=3306
echo.
echo # Media ^& Static ^(Local Development^)
echo HOST_URL=http://127.0.0.1:8000
echo.
echo # CORS Settings ^(Local Development^)
echo CORS_ALLOWED_ORIGINS=http://localhost:4200,http://127.0.0.1:4200
echo CORS_ORIGIN_ALLOW_ALL=True
) > .env

echo.
echo .env file created successfully!
echo.
echo Next steps:
echo 1. Make sure database 'cheradip_cheradip' exists in phpMyAdmin
echo 2. Run: python manage.py migrate
echo 3. Run: python manage.py runserver
echo.
pause

