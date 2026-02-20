# ✅ Local XAMPP Setup - Complete Checklist

## Quick Setup Summary

Your project is now configured for local XAMPP development. Follow these steps to get everything running:

## ✅ Pre-Setup Checklist

Before starting, ensure:
- [ ] XAMPP is installed
- [ ] MySQL service is running in XAMPP Control Panel (green)
- [ ] Python 3.8+ is installed
- [ ] Virtual environment is activated (recommended)

## Step-by-Step Setup

### 1️⃣ Create Database
```
Open phpMyAdmin → New → Database name: cheradip_cheradip → Collation: utf8mb4_unicode_ci → Create
```

### 2️⃣ Create .env File

**Easiest Method - Use Script:**
```bash
cd bcheradip
# Windows:
create_env_file.bat

# Linux/Mac:
chmod +x create_env_file.sh
./create_env_file.sh
```

**Or create manually** - See `.env.local.example` content in documentation

### 3️⃣ Install Dependencies
```bash
cd bcheradip
pip install -r requirements.txt
```

### 4️⃣ Run Migrations
```bash
python manage.py migrate
```

This creates **all tables** in your `cheradip_cheradip` database.

### 5️⃣ Create Admin User
```bash
python manage.py createsuperuser
```

### 6️⃣ Start Server
```bash
python manage.py runserver
```

Server runs at: **http://127.0.0.1:8000**

## ✅ Verification

### Test These URLs:

1. **API Root**: `http://127.0.0.1:8000/api/`
2. **Subjects**: `http://127.0.0.1:8000/api/subjects/`
3. **Groups**: `http://127.0.0.1:8000/api/groups/`
4. **Questions**: `http://127.0.0.1:8000/api/questions/`
5. **Admin**: `http://127.0.0.1:8000/admin/`

### Check Database Tables:

Open phpMyAdmin → `cheradip_cheradip` → Should see:

**Core Tables** (~10 tables):
- `auth_*` tables
- `django_*` tables
- `authtoken_token`

**Application Tables** (~20+ tables):
- `cheradip_group`
- `cheradip_subject`
- `cheradip_chapter`
- `cheradip_topic`
- `cheradip_institute`
- `cheradip_year`
- `cheradip_mcq_ict` ⭐ Main questions table
- `cheradip_mcq_ict_institutes` (ManyToMany)
- `cheradip_mcq_ict_years` (ManyToMany)
- `cheradip_customers`
- `cheradip_item`
- `cheradip_order`
- And more...

## 📋 All API Endpoints Available

### MCQ Questions
- `GET /api/questions/` - List all questions
- `POST /api/questions/` - Create question
- `GET /api/questions/{qid}/` - Get question
- `PUT /api/questions/{qid}/` - Update question
- `PATCH /api/questions/{qid}/` - Partial update
- `DELETE /api/questions/{qid}/` - Delete question
- `GET /api/questions/statistics/` - Get statistics

### Related Data
- `GET /api/groups/` - Academic groups
- `GET /api/subjects/` - Subjects (filter: `?groups=S,A,B`)
- `GET /api/chapters/` - Chapters (filter: `?subjects=275,101`)
- `GET /api/topics/` - Topics (filter: `?chapters=1,2,3`)
- `GET /api/instituteTypes/` - Institutes
- `GET /api/years/` - Years

### Authentication
- `POST /api/signup/` - Register
- `POST /api/login/` - Login
- `POST /api/profile_update/` - Update profile
- `POST /api/password_update/` - Update password
- `POST /api/mobile_update/` - Update mobile

### Other
- `GET /api/item/` - Products
- `GET /api/notification/` - Notifications
- `GET /api/institutes/` - Institute search
- `GET /api/divisions/` - Divisions
- `GET /api/districts/?division=Dhaka` - Districts
- `GET /api/thanas/?division=Dhaka&district=Dhaka` - Thanas

## 🔧 Configuration Files Updated

### Backend (Django)
- ✅ `backend/settings.py` - Updated for environment variables, XAMPP defaults
- ✅ `cheradip/models.py` - All models ready
- ✅ `cheradip/serializers.py` - All serializers created
- ✅ `cheradip/views.py` - All ViewSets created
- ✅ `cheradip/urls.py` - All endpoints registered
- ✅ `.env` - Will be created by setup script

### Frontend (Angular)
- ✅ `environment.ts` - Uses `http://127.0.0.1:8000/api`
- ✅ `environment.prod.ts` - Uses `https://cheradip.com/api`
- ✅ `api.service.ts` - Uses `environment.apiUrl`

## 📝 Example .env File Content

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

## 🎯 Quick Test Commands

### Test API (PowerShell):
```powershell
# Test subjects endpoint
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/subjects/" | Select-Object -ExpandProperty Content

# Test questions endpoint
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/questions/" | Select-Object -ExpandProperty Content

# Test groups endpoint
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/groups/" | Select-Object -ExpandProperty Content
```

### Test API (curl):
```bash
curl http://127.0.0.1:8000/api/subjects/
curl http://127.0.0.1:8000/api/questions/
curl http://127.0.0.1:8000/api/groups/
```

## 🐛 Common Issues & Quick Fixes

### Database Connection Failed
```bash
# Check MySQL is running in XAMPP
# Verify database name in .env matches phpMyAdmin
# Check username/password in .env
```

### Module Not Found: decouple
```bash
pip install python-decouple
```

### Migration Errors
```bash
# Check migration status
python manage.py showmigrations

# If needed, reset and re-run
python manage.py migrate --run-syncdb
```

### Port Already in Use
```bash
# Use different port
python manage.py runserver 8001
```

## 📚 Documentation Files

- `STEP_BY_STEP_XAMPP_SETUP.md` - Detailed step-by-step guide
- `XAMPP_SETUP.md` - Comprehensive setup guide
- `QUICK_START_XAMPP.md` - Quick reference
- `API_REFERENCE.md` - Complete API documentation
- `ENVIRONMENT_SETUP.md` - Environment configuration
- `IMPROVEMENTS_SUMMARY.md` - All improvements made

## ✅ Success Indicators

You'll know everything is working when:

1. ✅ Django server starts without errors
2. ✅ `http://127.0.0.1:8000/api/subjects/` returns JSON (even if empty)
3. ✅ Admin panel is accessible
4. ✅ Can login to admin panel
5. ✅ All `cheradip_*` tables exist in database
6. ✅ Frontend can connect (no CORS errors)

## 🚀 Next Steps

1. **Add Sample Data**: Use admin panel or Django shell
2. **Test API Endpoints**: Use browser or Postman
3. **Test Frontend**: Start Angular app and verify connection
4. **Create Questions**: Add sample MCQ questions through admin
5. **Test Authentication**: Test signup/login endpoints

## 📞 Need Help?

- Check `STEP_BY_STEP_XAMPP_SETUP.md` for detailed instructions
- Check `XAMPP_SETUP.md` for troubleshooting
- Verify all prerequisites are met
- Check Django server logs for errors
- Verify database connection in phpMyAdmin

---

**Setup Status**: ✅ Ready for local development  
**Database**: `cheradip_cheradip` (XAMPP MySQL)  
**Backend URL**: `http://127.0.0.1:8000/api`  
**Frontend URL**: `http://localhost:4200` (when running)

