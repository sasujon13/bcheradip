#!/bin/bash
# Create .env file for XAMPP local development
# Run this file in the bcheradip directory

cat > .env << 'EOF'
# XAMPP Local Development Configuration
# Generated automatically

# Django Settings
SECRET_KEY=django-insecure-d37cp#^cs90*bzhh+pvvv$6+h$tm@crx6$=_*^=d&g)k@+c%rj
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database Configuration (XAMPP Default)
DATABASE_NAME=cheradip_cheradip
DATABASE_USER=root
DATABASE_PASSWORD=
DATABASE_HOST=localhost
DATABASE_PORT=3306

# Media & Static (Local Development)
HOST_URL=http://127.0.0.1:8000

# CORS Settings (Local Development)
CORS_ALLOWED_ORIGINS=http://localhost:4200,http://127.0.0.1:4200
CORS_ORIGIN_ALLOW_ALL=True
EOF

echo ".env file created successfully!"
echo ""
echo "Next steps:"
echo "1. Make sure database 'cheradip_cheradip' exists in phpMyAdmin"
echo "2. Run: python manage.py migrate"
echo "3. Run: python manage.py runserver"

