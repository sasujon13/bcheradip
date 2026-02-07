# Step-by-Step XAMPP Setup Guide

## Overview
This guide will help you set up the Cheradip Django backend to work with XAMPP MySQL server locally.

## Step 1: Prerequisites Check

✅ **XAMPP Installed**: Download from https://www.apachefriends.org/ if not installed  
✅ **Python 3.8+**: Check with `python --version`  
✅ **XAMPP MySQL Running**: Open XAMPP Control Panel, start MySQL service (green = running)

## Step 2: Create Database in phpMyAdmin

1. Open XAMPP Control Panel
2. Click **"Admin"** button next to MySQL (or open `http://localhost/phpmyadmin`)
3. Click **"New"** in the left sidebar
4. Enter database name: **`cheradip_cheradip`**
5. Select **Collation**: `utf8mb4_unicode_ci` (important for Bengali text)
6. Click **"Create"** button

**Verify**: You should see `cheradip_cheradip` in the left sidebar.

## Step 3: Create .env File

### Option A: Use Setup Script (Easiest)

**Windows:**
```bash
cd bcheradip
create_env_file.bat
```

**Linux/Mac:**
```bash
cd bcheradip
chmod +x create_env_file.sh
./create_env_file.sh
```

### Option B: Use Python Setup Script
```bash
cd bcheradip
python setup_local.py
```

### Option C: Create Manually

Create a file named `.env` in the `bcheradip` directory (same folder as `manage.py`) with this content:

```env
SECRET_KEY=django-insecure-d37cp#^cs90*bzhh+pvvv$6+h$tm@crx6$=_*^=d&g)k@+c%rj
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DATABASE_NAME=cheradip_cheradip
DATABASE_USER=root
DATABASE_PASSWORD=
DATABASE_HOST=localhost
DATABASE_PORT=3306

HOST_URL=http://127.0.0.1:8000

CORS_ALLOWED_ORIGINS=http://localhost:4200,http://127.0.0.1:4200
CORS_ORIGIN_ALLOW_ALL=True
```

**Important**: 
- If you set a MySQL root password in XAMPP, update `DATABASE_PASSWORD=yourpassword`
- The `.env` file should be in `bcheradip/.env` (same directory as `manage.py`)

## Step 4: Install Python Dependencies

```bash
cd bcheradip

# Activate virtual environment (if using one)
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify python-decouple is installed
pip list | findstr decouple
# or on Linux/Mac: pip list | grep decouple
```

**Expected output**: Should see `python-decouple` in the list.

## Step 5: Run Database Migrations

This step creates all tables in your `cheradip_cheradip` database:

```bash
cd bcheradip

# Check migration status (optional)
python manage.py showmigrations

# Create migrations (if needed)
python manage.py makemigrations

# Apply migrations (creates all tables)
python manage.py migrate
```

**Expected Output:**
```
Operations to perform:
  Apply all migrations: admin, auth, authtoken, cheradip, contenttypes, sessions
Running migrations:
  Applying contenttypes.0001_initial... OK
  Applying auth.0001_initial... OK
  Applying admin.0001_initial... OK
  Applying admin.0002_logentry_remove_auto_add... OK
  Applying admin.0003_logentry_add_action_flag_choices... OK
  Applying authtoken.0001_initial... OK
  Applying authtoken.0002_auto_20160226_1747... OK
  Applying authtoken.0003_tokenproxy... OK
  Applying cheradip.0001_initial... OK
  Applying cheradip.0002_rename_institute_mcq_ict_institutes... OK
  Applying cheradip.0003_rename_years_mcq_ict_year... OK
  Applying cheradip.0004_rename_year_mcq_ict_years... OK
  Applying sessions.0001_initial... OK
```

**Verify in phpMyAdmin**:
1. Open phpMyAdmin
2. Click on `cheradip_cheradip` database
3. Check that tables starting with `cheradip_` are created
4. You should see at least 20+ tables

## Step 6: Create Superuser (Admin Account)

```bash
python manage.py createsuperuser
```

Follow the prompts:
- Username: (enter admin username, e.g., `admin`)
- Email address: (optional, press Enter to skip)
- Password: (enter password, it won't show)
- Password (again): (confirm password)

**Note**: Username can be a mobile number or email. For XAMPP local development, any username works.

## Step 7: Start Django Development Server

```bash
python manage.py runserver
```

**Expected Output:**
```
Watching for file changes with StatReloader
Performing system checks...

System check identified no issues (0 silenced).
January 01, 2024 - 10:00:00
Django version 5.2.5, using settings 'backend.settings'
Starting development server at http://127.0.0.1:8000/
Quit the server with CTRL-BREAK.
```

✅ **Server is running!** Keep this terminal window open.

## Step 8: Verify Backend Setup

Open these URLs in your browser:

### Test API Endpoints:
1. **Subjects**: `http://127.0.0.1:8000/api/subjects/`
   - Should return: `[]` (empty list if no data) or JSON array

2. **Groups**: `http://127.0.0.1:8000/api/groups/`
   - Should return: `[]` or JSON array

3. **Questions**: `http://127.0.0.1:8000/api/questions/`
   - Should return: Paginated response with `{"count": 0, "results": [], ...}`

4. **Admin Panel**: `http://127.0.0.1:8000/admin/`
   - Should show login page
   - Login with superuser credentials from Step 6

### Verify Database Tables:

Open phpMyAdmin → `cheradip_cheradip` → Check for these tables:

**Core Django Tables:**
- `auth_group`, `auth_permission`, `auth_user`, etc.
- `django_admin_log`, `django_content_type`, `django_migrations`, `django_session`
- `authtoken_token`

**Application Tables:**
- `cheradip_group` ✅
- `cheradip_subject` ✅
- `cheradip_chapter` ✅
- `cheradip_topic` ✅
- `cheradip_institute` ✅
- `cheradip_year` ✅
- `cheradip_mcq_ict` ✅ (Main questions table)
- `cheradip_mcq_ict_institutes` ✅ (ManyToMany)
- `cheradip_mcq_ict_years` ✅ (ManyToMany)
- `cheradip_customer` ✅
- `cheradip_item` ✅
- `cheradip_order` ✅
- `cheradip_orderdetail` ✅
- `cheradip_transaction` ✅
- `cheradip_notification` ✅
- And more...

## Step 9: Configure Frontend (Angular)

The frontend is already configured! Just verify:

1. **Check `environment.ts`** - Should have:
   ```typescript
   apiUrl: 'http://127.0.0.1:8000/api'
   ```

2. **Check `api.service.ts`** - Should use:
   ```typescript
   private baseUrl = environment.apiUrl;
   ```

3. **Start Angular Development Server**:
   ```bash
   cd fcheradip
   ng serve
   ```

4. **Access Frontend**: `http://localhost:4200`

## Step 10: Test Full Integration

1. **Backend running**: `http://127.0.0.1:8000`
2. **Frontend running**: `http://localhost:4200`
3. **Test API calls from frontend**
4. **Verify CORS works** (no CORS errors in browser console)

## Troubleshooting Common Issues

### Issue: `ModuleNotFoundError: No module named 'decouple'`
```bash
pip install python-decouple
```

### Issue: `django.db.utils.OperationalError: (1045, "Access denied")`
**Check:**
- MySQL is running in XAMPP
- Username is `root`
- Password matches `.env` (empty by default)
- Update `.env` if password is set

### Issue: `django.db.utils.OperationalError: (1049, "Unknown database")`
**Solution:**
1. Open phpMyAdmin
2. Create database `cheradip_cheradip`
3. Verify name is exactly `cheradip_cheradip` (lowercase)

### Issue: `django.db.utils.OperationalError: (2002, "Can't connect")`
**Solution:**
- Check XAMPP Control Panel - MySQL must be green (running)
- Verify port 3306 is not used by another application
- Check `DATABASE_HOST=localhost` in `.env`

### Issue: Migration errors with ForeignKey
**Solution:**
- Make sure all migrations are run in order
- Check `python manage.py showmigrations` shows all applied
- Try: `python manage.py migrate --run-syncdb`

### Issue: CORS errors in browser
**Solution:**
- Verify `.env` has `CORS_ORIGIN_ALLOW_ALL=True` for development
- Or add `http://localhost:4200` to `CORS_ALLOWED_ORIGINS`
- Restart Django server after changing `.env`

### Issue: Port 8000 already in use
**Solution:**
```bash
# Use different port
python manage.py runserver 8001

# Or kill process using port 8000 (Windows)
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

## Verification Checklist

After completing all steps, verify:

- [ ] Database `cheradip_cheradip` exists in phpMyAdmin
- [ ] All `cheradip_*` tables exist (check count ~20+ tables)
- [ ] Django server runs without errors
- [ ] API endpoint `http://127.0.0.1:8000/api/subjects/` returns JSON
- [ ] Admin panel `http://127.0.0.1:8000/admin/` is accessible
- [ ] Can login to admin panel
- [ ] Frontend can connect to backend (no CORS errors)
- [ ] Environment variables loaded from `.env` file

## Adding Sample Data (Optional)

### Via Admin Panel:
1. Login to `http://127.0.0.1:8000/admin/`
2. Click on any model (e.g., "Groups")
3. Click "Add Group"
4. Fill in data and save

### Via Django Shell:
```bash
python manage.py shell
```

```python
from cheradip.models import Group, Subject, Chapter, Topic, Institute, Year

# Create a group
group_s = Group.objects.create(group_code='S', group_name='Science')
group_a = Group.objects.create(group_code='A', group_name='Humanities')
group_b = Group.objects.create(group_code='B', group_name='Business Studies')

# Create a subject
subject = Subject.objects.create(subject_code='275', subject_name='ICT')
subject.group.add(group_s, group_a, group_b)

# Create a chapter
chapter = Chapter.objects.create(
    subject=subject,
    chapter_no='01',
    chapter_name='Introduction to ICT'
)

# Create a topic
topic = Topic.objects.create(
    chapter=chapter,
    topic_no='01',
    topic_name='Basic Concepts'
)

# Create an institute
institute = Institute.objects.create(
    institute_code='INST001',
    institute_name='Sample Institute',
    institute_type='Government'
)

# Create a year
year = Year.objects.create(year_code='2024', year_name='2024')

print("Sample data created successfully!")
```

## Quick Command Reference

```bash
# Navigate to backend
cd bcheradip

# Create .env file (Windows)
create_env_file.bat

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start server
python manage.py runserver

# Check migration status
python manage.py showmigrations

# Open Django shell
python manage.py shell

# Create new migration (after model changes)
python manage.py makemigrations

# Collect static files
python manage.py collectstatic

# Check database
python manage.py dbshell
```

## Expected API Response Examples

### Empty Database (No Data):
```json
{
  "count": 0,
  "next": null,
  "previous": null,
  "results": []
}
```

### With Data:
```json
{
  "count": 10,
  "next": "http://127.0.0.1:8000/api/questions/?page=2",
  "previous": null,
  "results": [
    {
      "qid": "2750101001",
      "subject": {...},
      "chapter": {...},
      "question": "Question text...",
      ...
    }
  ]
}
```

## Next Steps After Setup

1. ✅ Add sample data through admin panel
2. ✅ Test all API endpoints
3. ✅ Test frontend-backend connection
4. ✅ Create sample questions
5. ✅ Test authentication endpoints
6. ✅ Verify image upload works
7. ✅ Test filtering and search

## Database Schema Summary

**Main Question Table**: `cheradip_mcq_ict`
- Primary Key: `qid` (auto-generated: subject_code + chapter_no + topic_no + sequence)
- Foreign Keys: `subject`, `chapter`, `topic`
- ManyToMany: `institutes`, `years`
- Images: `img_uddipok`, `img_question`, `img_explanation`

**Hierarchical Structure**:
```
Group (S, A, B, I, H, M)
  └─ Subject (275, 101, 102, ...)
      └─ Chapter (01, 02, 03, ...)
          └─ Topic (01, 02, 03, ...)
              └─ Mcq_ict (Questions)
```

## Support

If you encounter issues:
1. Check `XAMPP_SETUP.md` for detailed troubleshooting
2. Verify all steps completed successfully
3. Check Django server logs for errors
4. Verify database connection in phpMyAdmin
5. Check `.env` file exists and has correct values

---

**Setup Time**: ~10-15 minutes  
**Difficulty**: Beginner-friendly  
**Last Updated**: After XAMPP local setup configuration

