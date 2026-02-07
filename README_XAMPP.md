# Cheradip Backend - XAMPP Local Development Setup

## 🎯 Quick Start (3 Steps)

### Step 1: Create Database
1. Open **phpMyAdmin**: `http://localhost/phpmyadmin`
2. Create database: **`cheradip_cheradip`** (Collation: `utf8mb4_unicode_ci`)

### Step 2: Create .env File
Run: `create_env_file.bat` (Windows) or `./create_env_file.sh` (Linux/Mac)

Or create `.env` manually in `bcheradip` folder:
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

### Step 3: Run Setup
```bash
cd bcheradip
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser  # Optional
python manage.py runserver
```

**That's it!** Your API is now running at `http://127.0.0.1:8000/api/`

## 📋 All Tables Created

After running migrations, these tables will be created in `cheradip_cheradip`:

### MCQ Question Tables
- `cheradip_group` - Academic groups (S=Science, A=Humanities, B=Business, etc.)
- `cheradip_subject` - Subjects (101, 102, 275, etc.)
- `cheradip_chapter` - Chapters for each subject
- `cheradip_topic` - Topics for each chapter
- `cheradip_mcq_ict` - **Main MCQ questions table**
- `cheradip_mcq_ict_institutes` - Question-Institute relationships (ManyToMany)
- `cheradip_mcq_ict_years` - Question-Year relationships (ManyToMany)
- `cheradip_institute` - Institutes
- `cheradip_year` - Exam years

### User & E-commerce Tables
- `cheradip_customer` - User accounts
- `cheradip_item` - Products/Items
- `cheradip_order` - Orders
- `cheradip_orderdetail` - Order details
- `cheradip_transaction` - Transactions
- `cheradip_ordered` - Completed orders
- `cheradip_canceled` - Canceled orders

### Other Tables
- `cheradip_notification` - Notifications
- `cheradip_institutes` - Banbeis institute data
- `cheradip_token` - Tokens
- `cheradip_merit`, `cheradip_merit5`, `cheradip_merit6` - Merit lists
- `cheradip_vacancy`, `cheradip_vacancy5`, `cheradip_vacancy6` - Vacancy lists
- `cheradip_recommend`, `cheradip_recommend5`, `cheradip_recommend6` - Recommendations
- `cheradip_banbeis` - Banbeis data

### Django System Tables
- `auth_*` - Authentication tables
- `django_*` - Django system tables
- `authtoken_token` - REST Framework tokens

## 🌐 All API Endpoints

### Base URL
```
Local: http://127.0.0.1:8000/api/
```

### MCQ Question Endpoints
```
GET    /api/questions/              - List all questions
POST   /api/questions/              - Create question
GET    /api/questions/{qid}/        - Get question
PUT    /api/questions/{qid}/        - Update question
PATCH  /api/questions/{qid}/        - Partial update
DELETE /api/questions/{qid}/        - Delete question
GET    /api/questions/statistics/   - Get statistics
```

### Question Filtering
```
?subject=101&subject=275        - Filter by subject codes
?chapter=01&chapter=02          - Filter by chapter numbers
?topic=01                       - Filter by topic numbers
?institute=INST001              - Filter by institute codes
?year=2024                      - Filter by year codes
?group=S&group=A                - Filter by group codes
?search=question text           - Search in questions
?qid=2750101001                 - Get specific question
?page=1&page_size=20            - Pagination
```

### Related Data Endpoints
```
GET /api/groups/                    - List groups
GET /api/groups/?group_code=S       - Get specific group

GET /api/subjects/                  - List subjects
GET /api/subjects/?groups=S,A,B     - Filter by groups
GET /api/subjects/?subject_code=275 - Get specific subject

GET /api/chapters/                  - List chapters
GET /api/chapters/?subjects=275,101 - Filter by subjects
GET /api/chapters/?chapter_no=01    - Filter by chapter number

GET /api/topics/                    - List topics
GET /api/topics/?chapters=1,2,3     - Filter by chapter IDs
GET /api/topics/?topic_no=01        - Filter by topic number

GET /api/instituteTypes/            - List institutes
GET /api/instituteTypes/?institute_code=INST001
GET /api/instituteTypes/?institute_type=Type1

GET /api/years/                     - List years
GET /api/years/?year_code=2024      - Get specific year
GET /api/years/?institutes=INST001  - Filter by institutes
```

### Authentication Endpoints
```
POST /api/signup/           - Register new user
POST /api/login/            - Login (returns authToken)
POST /api/profile_update/   - Update profile
POST /api/password_update/  - Update password
POST /api/mobile_update/    - Update mobile number
GET  /api/username/?username=01712345678 - Check if exists
GET  /api/password/?username=01712345678&password=pass - Verify password
```

### Other Endpoints
```
GET /api/item/                    - Products
GET /api/notification/            - Notifications
GET /api/institutes/              - Institute search
GET /api/divisions/               - Divisions
GET /api/districts/?division=Dhaka - Districts
GET /api/thanas/?division=Dhaka&district=Dhaka - Thanas
GET /api/myorder/{username}/      - User orders
```

## 🧪 Testing Endpoints

### Test in Browser
Open these URLs:
- `http://127.0.0.1:8000/api/subjects/`
- `http://127.0.0.1:8000/api/groups/`
- `http://127.0.0.1:8000/api/questions/`
- `http://127.0.0.1:8000/api/chapters/`
- `http://127.0.0.1:8000/api/topics/`

### Test with curl
```bash
curl http://127.0.0.1:8000/api/subjects/
curl http://127.0.0.1:8000/api/questions/
curl http://127.0.0.1:8000/api/groups/
```

### Test with PowerShell
```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/subjects/" | Select-Object -ExpandProperty Content
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/questions/" | Select-Object -ExpandProperty Content
```

## 📊 Database Schema Overview

### MCQ Question Structure
```
Group (S, A, B, I, H, M)
  └─ Subject (101, 102, 275, ...)
      └─ Chapter (01, 02, 03, ...)
          └─ Topic (01, 02, 03, ...)
              └─ Mcq_ict (Questions)
                  ├─ institutes (ManyToMany)
                  └─ years (ManyToMany)
```

### Question ID Format
Questions have auto-generated IDs:
- Format: `{subject_code}{chapter_no}{topic_no}{sequence}`
- Example: `2750101001` = Subject 275, Chapter 01, Topic 01, Question 001
- Example: `1010203005` = Subject 101, Chapter 02, Topic 03, Question 005

## 🔑 Important Notes

### Default XAMPP Configuration
- **Host**: `localhost`
- **Port**: `3306`
- **User**: `root`
- **Password**: (empty by default)
- **Database**: `cheradip_cheradip`

### If MySQL Has Password
If you set a MySQL root password, update `.env`:
```env
DATABASE_PASSWORD=your_mysql_password
```

### Frontend Configuration
Angular frontend is already configured:
- **Development**: Uses `http://127.0.0.1:8000/api` (from `environment.ts`)
- **Production**: Uses `https://cheradip.com/api` (from `environment.prod.ts`)

No changes needed in frontend code!

## 🚀 Running the Project

### Backend (Django)
```bash
cd bcheradip
python manage.py runserver
```
Backend runs at: **http://127.0.0.1:8000**

### Frontend (Angular)
```bash
cd fcheradip
ng serve
```
Frontend runs at: **http://localhost:4200**

## ✅ Verification Checklist

After setup, verify:
- [ ] Database `cheradip_cheradip` exists
- [ ] All `cheradip_*` tables created (~20+ tables)
- [ ] Django server starts without errors
- [ ] API endpoints return JSON (even if empty)
- [ ] Admin panel accessible at `/admin/`
- [ ] Can login to admin panel
- [ ] Frontend can connect (no CORS errors)

## 📚 Documentation Files

- `STEP_BY_STEP_XAMPP_SETUP.md` - Detailed step-by-step guide
- `QUICK_START_XAMPP.md` - Quick reference guide
- `XAMPP_SETUP.md` - Comprehensive setup with troubleshooting
- `API_REFERENCE.md` - Complete API documentation
- `LOCAL_SETUP_COMPLETE.md` - Setup checklist
- `ENVIRONMENT_SETUP.md` - Environment variables guide

## 🐛 Quick Troubleshooting

| Issue | Solution |
|-------|----------|
| Can't connect to MySQL | Check XAMPP MySQL is running (green) |
| Unknown database | Create `cheradip_cheradip` in phpMyAdmin |
| Module 'decouple' not found | Run: `pip install python-decouple` |
| Access denied | Check `.env` DATABASE_USER and DATABASE_PASSWORD |
| Port 8000 in use | Use: `python manage.py runserver 8001` |
| CORS errors | Verify `CORS_ORIGIN_ALLOW_ALL=True` in `.env` |

## 🎉 Success!

Once everything is set up:
- ✅ All tables created in database
- ✅ All API endpoints working
- ✅ Frontend connected to backend
- ✅ Ready for development!

---

**Need Help?** Check `STEP_BY_STEP_XAMPP_SETUP.md` for detailed instructions.

