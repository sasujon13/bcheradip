# XAMPP Local Development Setup Guide

## Prerequisites
- XAMPP installed and running
- MySQL service started in XAMPP Control Panel
- Python 3.8+ installed
- Virtual environment activated (recommended)

## Step 1: Create Database in XAMPP

1. Open **phpMyAdmin** (usually at `http://localhost/phpmyadmin`)
2. Click on **"New"** in the left sidebar
3. Enter database name: `cheradip_cheradip`
4. Select **Collation**: `utf8mb4_general_ci` or `utf8mb4_unicode_ci`
5. Click **"Create"**

Alternatively, use MySQL command line:
```sql
CREATE DATABASE cheradip_cheradip CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## Step 2: Configure Environment Variables

Create a `.env` file in the `bcheradip` directory (same level as `manage.py`):

```env
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
```

**Note**: If you set a password for MySQL root user in XAMPP, update `DATABASE_PASSWORD` accordingly.

## Step 3: Install Dependencies

```bash
cd bcheradip
pip install -r requirements.txt
```

Make sure `python-decouple` is installed:
```bash
pip install python-decouple
```

## Step 4: Run Migrations

This will create all tables in your local database:

```bash
# Make migrations (if you've made model changes)
python manage.py makemigrations

# Apply migrations to create all tables
python manage.py migrate
```

**Expected Output:**
```
Operations to perform:
  Apply all migrations: admin, auth, authtoken, cheradip, contenttypes, sessions
Running migrations:
  Applying contenttypes.0001_initial... OK
  Applying auth.0001_initial... OK
  ...
  Applying cheradip.0001_initial... OK
  Applying cheradip.0002_rename_institute_mcq_ict_institutes... OK
  Applying cheradip.0003_rename_years_mcq_ict_year... OK
  Applying cheradip.0004_rename_year_mcq_ict_years... OK
  ...
```

## Step 5: Create Superuser (Optional but Recommended)

```bash
python manage.py createsuperuser
```

Follow the prompts to create an admin user.

## Step 6: Run Development Server

```bash
python manage.py runserver
```

Your API will be available at: `http://127.0.0.1:8000/api/`

## Step 7: Verify Database Tables

Open phpMyAdmin and check that these tables exist in `cheradip_cheradip` database:

### Core Tables:
- `auth_*` - Django authentication tables
- `django_*` - Django system tables
- `authtoken_token` - REST Framework token table

### Application Tables:
- `cheradip_item`
- `cheradip_customers`
- `cheradip_order`
- `cheradip_orderdetail`
- `cheradip_transaction`
- `cheradip_ordered`
- `cheradip_canceled`
- `cheradip_group`
- `cheradip_subject`
- `cheradip_chapter`
- `cheradip_topic`
- `cheradip_institute`
- `cheradip_year`
- `cheradip_mcq_ict`
- `cheradip_mcq_ict_institutes` (ManyToMany)
- `cheradip_mcq_ict_years` (ManyToMany)
- `cheradip_notification`
- `cheradip_institutes`
- `cheradip_token`
- `cheradip_banbeis`
- `cheradip_merit`
- `cheradip_merit5`
- `cheradip_merit6`
- `cheradip_recommend`
- `cheradip_recommend5`
- `cheradip_recommend6`
- `cheradip_vacancy`
- `cheradip_vacancy5`
- `cheradip_vacancy6`

## Testing API Endpoints

### Test Basic Endpoint
```bash
# In browser or using curl
http://127.0.0.1:8000/api/subjects/

# Using curl
curl http://127.0.0.1:8000/api/subjects/

# Using PowerShell (Windows)
Invoke-WebRequest -Uri http://127.0.0.1:8000/api/subjects/
```

### Test Questions Endpoint
```bash
http://127.0.0.1:8000/api/questions/
```

### Test Admin Panel
```
http://127.0.0.1:8000/admin/
```
Login with superuser credentials created in Step 5.

## Troubleshooting

### Issue: `ModuleNotFoundError: No module named 'decouple'`
**Solution**: 
```bash
pip install python-decouple
```

### Issue: `django.db.utils.OperationalError: (1045, "Access denied")`
**Solution**: 
1. Check MySQL username and password in `.env`
2. Default XAMPP MySQL user is `root` with empty password
3. If you set a password, update `DATABASE_PASSWORD` in `.env`

### Issue: `django.db.utils.OperationalError: (1049, "Unknown database 'cheradip_cheradip'")`
**Solution**: 
1. Create database first in phpMyAdmin (see Step 1)
2. Verify database name in `.env` matches exactly

### Issue: `django.db.utils.OperationalError: (2002, "Can't connect to MySQL server")`
**Solution**: 
1. Make sure XAMPP MySQL service is running
2. Check `DATABASE_HOST` in `.env` is `localhost`
3. Check `DATABASE_PORT` is `3306` (XAMPP default)

### Issue: `mysqlclient` installation error on Windows
**Solution**: 
Use PyMySQL instead (already in requirements.txt):
```bash
pip install PyMySQL
```
The project already configures PyMySQL in settings.py

### Issue: Migration errors
**Solution**: 
If migrations fail, you can reset:
```bash
# Delete migration files (keep __init__.py)
# Then recreate:
python manage.py makemigrations
python manage.py migrate
```

### Issue: Permission denied errors
**Solution**: 
Make sure the database user has proper permissions:
```sql
GRANT ALL PRIVILEGES ON cheradip_cheradip.* TO 'root'@'localhost';
FLUSH PRIVILEGES;
```

## Database Connection Settings Summary

For XAMPP default installation:
- **Host**: `localhost` or `127.0.0.1`
- **Port**: `3306`
- **User**: `root`
- **Password**: (empty, or your XAMPP MySQL root password)
- **Database**: `cheradip_cheradip`

## Next Steps

1. ✅ Verify all tables are created
2. ✅ Test API endpoints
3. ✅ Add sample data through admin panel
4. ✅ Test frontend connection (Angular app on localhost:4200)
5. ✅ Configure frontend API base URL to `http://127.0.0.1:8000/api`

## Frontend Configuration

Update your Angular frontend `environment.ts`:
```typescript
export const environment = {
    production: false,
    apiUrl: 'http://127.0.0.1:8000/api'
};
```

And update `api.service.ts`:
```typescript
private baseUrl = 'http://127.0.0.1:8000/api';  // Local development
// private baseUrl = 'https://cheradip.com/api';  // Production
```

## Additional Commands

### Collect Static Files (if needed)
```bash
python manage.py collectstatic --noinput
```

### Create Sample Data (if needed)
```bash
python manage.py shell
```
Then use Django ORM to create sample data.

### Check Database Connection
```bash
python manage.py dbshell
```
This opens MySQL command line interface.

### View Migration Status
```bash
python manage.py showmigrations
```

### Create Migration for Model Changes
```bash
python manage.py makemigrations cheradip
python manage.py migrate
```

---

**Note**: Keep XAMPP MySQL service running while developing!

