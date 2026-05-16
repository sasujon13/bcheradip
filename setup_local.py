#!/usr/bin/env python
"""
Setup script for local XAMPP development environment
This script helps set up the Django project with XAMPP MySQL database
"""

import os
import subprocess
import sys

def create_env_file():
    """Create .env file for local XAMPP development"""
    env_content = """# XAMPP Local Development Configuration
# Generated automatically by setup_local.py

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

# CORS Settings (Local Development - Allow Angular dev server)
CORS_ALLOWED_ORIGINS=http://localhost:4200,http://127.0.0.1:4200
CORS_ORIGIN_ALLOW_ALL=True
CSRF_TRUSTED_ORIGINS=http://localhost:4200,http://127.0.0.1:4200
"""
    
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    
    if os.path.exists(env_path):
        print("⚠️  .env file already exists. Skipping creation.")
        print("   If you want to recreate it, delete the existing .env file first.")
        return False
    
    try:
        with open(env_path, 'w') as f:
            f.write(env_content)
        print("✅ Created .env file successfully!")
        return True
    except Exception as e:
        print(f"❌ Error creating .env file: {e}")
        return False

def check_database_connection():
    """Check if database connection can be established"""
    try:
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
        django.setup()
        
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        print("✅ Database connection successful!")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("   Please ensure:")
        print("   1. XAMPP MySQL service is running")
        print("   2. Database 'cheradip_cheradip' exists")
        print("   3. MySQL credentials in .env are correct")
        return False

def run_migrations():
    """Run database migrations"""
    print("\n📦 Running migrations...")
    try:
        result = subprocess.run([sys.executable, 'manage.py', 'migrate'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Migrations completed successfully!")
            return True
        else:
            print(f"❌ Migration error:\n{result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error running migrations: {e}")
        return False

def create_superuser():
    """Prompt to create superuser"""
    response = input("\n❓ Do you want to create a superuser? (y/n): ").lower()
    if response == 'y':
        try:
            subprocess.run([sys.executable, 'manage.py', 'createsuperuser'])
            print("✅ Superuser created!")
        except Exception as e:
            print(f"❌ Error creating superuser: {e}")

def main():
    print("=" * 60)
    print("  Cheradip Backend - Local XAMPP Setup")
    print("=" * 60)
    
    # Step 1: Create .env file
    print("\n📝 Step 1: Creating .env file...")
    env_created = create_env_file()
    
    if not env_created:
        print("\n⚠️  Continuing with existing .env file...")
    
    # Step 2: Check database connection
    print("\n🔌 Step 2: Checking database connection...")
    if not check_database_connection():
        print("\n❌ Please fix database connection issues before continuing.")
        print("   See XAMPP_SETUP.md for detailed instructions.")
        return
    
    # Step 3: Run migrations
    print("\n📦 Step 3: Running database migrations...")
    if not run_migrations():
        print("\n❌ Migration failed. Please check the error messages above.")
        return
    
    # Step 4: Create superuser
    print("\n👤 Step 4: Creating superuser (optional)...")
    create_superuser()
    
    print("\n" + "=" * 60)
    print("  ✅ Setup Complete!")
    print("=" * 60)
    print("\n📋 Next Steps:")
    print("   1. Start the development server:")
    print("      python manage.py runserver")
    print("\n   2. Access admin panel:")
    print("      http://127.0.0.1:8000/admin/")
    print("\n   3. Test API endpoints:")
    print("      http://127.0.0.1:8000/api/subjects/")
    print("      http://127.0.0.1:8000/api/questions/")
    print("\n   4. Update frontend API base URL to:")
    print("      http://127.0.0.1:8000/api")
    print("\n" + "=" * 60)

if __name__ == '__main__':
    main()

