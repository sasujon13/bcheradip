# Quick Start Guide - XAMPP Local Development

## Prerequisites Checklist
- [ ] XAMPP installed and running
- [ ] MySQL service started in XAMPP Control Panel
- [ ] Python 3.8+ installed
- [ ] Database `cheradip_cheradip` created in phpMyAdmin

## Quick Setup (5 Minutes)

### Step 1: Create Database
1. Open **phpMyAdmin**: `http://localhost/phpmyadmin`
2. Click **"New"** → Database name: `cheradip_cheradip` → Collation: `utf8mb4_unicode_ci` → **Create**

### Step 2: Create .env File
Create `.env` file in `bcheradip` folder with this content:

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

**Note**: If your XAMPP MySQL root user has a password, add it to `DATABASE_PASSWORD=`

### Step 3: Install Dependencies
```bash
cd bcheradip
pip install -r requirements.txt
```

### Step 4: Run Setup Script (Optional)
```bash
python setup_local.py
```
This will:
- Create .env file (if not exists)
- Check database connection
- Run migrations
- Optionally create superuser

### Step 5: Or Manual Setup
```bash
# Make migrations
python manage.py makemigrations

# Run migrations (creates all tables)
python manage.py migrate

# Create superuser (optional)
python manage.py createsuperuser

# Run server
python manage.py runserver
```

### Step 6: Verify Setup
Open in browser:
- **API**: `http://127.0.0.1:8000/api/subjects/`
- **Admin**: `http://127.0.0.1:8000/admin/`
- **Questions**: `http://127.0.0.1:8000/api/questions/`

## Frontend Configuration

The Angular frontend is already configured to use:
- **Development**: `http://127.0.0.1:8000/api` (from `environment.ts`)
- **Production**: `https://cheradip.com/api` (from `environment.prod.ts`)

No changes needed! Just run your Angular app:
```bash
cd fcheradip
ng serve
```

## Expected Database Tables

After migrations, you should see these tables in `cheradip_cheradip`:

### Django Core Tables
- `auth_*` - Authentication tables
- `django_*` - Django system tables  
- `authtoken_token` - API tokens

### Application Tables
- ✅ `cheradip_group` - Academic groups (S, A, B, I, H, M)
- ✅ `cheradip_subject` - Subjects (101, 102, 275, etc.)
- ✅ `cheradip_chapter` - Chapters for each subject
- ✅ `cheradip_topic` - Topics for each chapter
- ✅ `cheradip_institute` - Institutes
- ✅ `cheradip_year` - Exam years
- ✅ `cheradip_mcq_ict` - MCQ questions (main table)
- ✅ `cheradip_mcq_ict_institutes` - Question-Institute relationships
- ✅ `cheradip_mcq_ict_years` - Question-Year relationships
- ✅ `cheradip_customers` - User accounts
- ✅ `cheradip_item` - Products/Items
- ✅ `cheradip_order` - Orders
- ✅ `cheradip_orderdetail` - Order details
- ✅ `cheradip_transaction` - Transactions
- ✅ `cheradip_notification` - Notifications
- ✅ `cheradip_institutes` - Institute data (Banbeis)
- ✅ `cheradip_token` - Tokens
- ✅ `cheradip_merit`, `cheradip_merit5`, `cheradip_merit6` - Merit lists
- ✅ `cheradip_vacancy`, `cheradip_vacancy5`, `cheradip_vacancy6` - Vacancy lists
- ✅ `cheradip_recommend`, `cheradip_recommend5`, `cheradip_recommend6` - Recommendations
- ✅ `cheradip_banbeis` - Banbeis institute data
- ✅ `cheradip_ordered` - Completed orders
- ✅ `cheradip_canceled` - Canceled orders

## Testing API Endpoints

### Test Subject Endpoint
```bash
# Browser
http://127.0.0.1:8000/api/subjects/

# PowerShell (Windows)
Invoke-WebRequest -Uri http://127.0.0.1:8000/api/subjects/ | Select-Object -ExpandProperty Content

# curl (Linux/Mac)
curl http://127.0.0.1:8000/api/subjects/
```

### Test Questions Endpoint
```bash
http://127.0.0.1:8000/api/questions/
http://127.0.0.1:8000/api/questions/?subject=275
http://127.0.0.1:8000/api/questions/?group=S
```

### Test Groups Endpoint
```bash
http://127.0.0.1:8000/api/groups/
```

### Test Chapters Endpoint
```bash
http://127.0.0.1:8000/api/chapters/?subjects=275
```

### Test Topics Endpoint
```bash
http://127.0.0.1:8000/api/topics/?chapters=1,2,3
```

## Common Issues & Solutions

### Issue 1: Can't connect to MySQL
**Solution**: 
- Check XAMPP Control Panel - MySQL service must be running (green)
- Verify MySQL port is 3306 (default)
- Check `DATABASE_HOST=localhost` in `.env`

### Issue 2: Unknown database error
**Solution**: 
- Create database in phpMyAdmin first (see Step 1)
- Verify database name matches exactly: `cheradip_cheradip`

### Issue 3: Access denied for user 'root'
**Solution**: 
- Default XAMPP MySQL root password is empty
- If you set a password, update `DATABASE_PASSWORD=yourpassword` in `.env`
- Or reset MySQL root password in XAMPP

### Issue 4: Module not found: 'decouple'
**Solution**:
```bash
pip install python-decouple
```

### Issue 5: Migration errors
**Solution**:
```bash
# Check migration status
python manage.py showmigrations

# If needed, fake initial migration
python manage.py migrate --fake-initial

# Or reset migrations (careful - deletes data)
# python manage.py migrate cheradip zero
# python manage.py migrate
```

### Issue 6: CORS errors in frontend
**Solution**:
- Verify `CORS_ALLOWED_ORIGINS` includes `http://localhost:4200`
- Or set `CORS_ORIGIN_ALLOW_ALL=True` in `.env` for development
- Restart Django server after changing `.env`

## Verification Checklist

After setup, verify:
- [ ] Database `cheradip_cheradip` exists in phpMyAdmin
- [ ] All tables created (check `cheradip_*` tables)
- [ ] Django server runs without errors
- [ ] API endpoint responds: `http://127.0.0.1:8000/api/subjects/`
- [ ] Admin panel accessible: `http://127.0.0.1:8000/admin/`
- [ ] Can login to admin panel (if superuser created)
- [ ] Frontend can connect (Angular app on port 4200)

## API Endpoints Summary

All endpoints are prefixed with `/api/`:

### MCQ Question Management
- `GET /api/questions/` - List all questions
- `POST /api/questions/` - Create question
- `GET /api/questions/{qid}/` - Get question
- `PUT /api/questions/{qid}/` - Update question
- `DELETE /api/questions/{qid}/` - Delete question
- `GET /api/questions/statistics/` - Get statistics

### Related Data
- `GET /api/subjects/` - List subjects
- `GET /api/chapters/` - List chapters
- `GET /api/topics/` - List topics
- `GET /api/groups/` - List groups
- `GET /api/instituteTypes/` - List institutes
- `GET /api/years/` - List years

### Authentication
- `POST /api/signup/` - Register
- `POST /api/login/` - Login
- `POST /api/profile_update/` - Update profile
- `POST /api/password_update/` - Update password

### Other
- `GET /api/item/` - Products
- `GET /api/notification/` - Notifications
- `GET /api/institutes/` - Institutes search
- See `API_REFERENCE.md` for complete documentation

## Development Workflow

1. **Start XAMPP MySQL** (if not already running)
2. **Start Django Backend**:
   ```bash
   cd bcheradip
   python manage.py runserver
   ```
3. **Start Angular Frontend** (in another terminal):
   ```bash
   cd fcheradip
   ng serve
   ```
4. **Access**:
   - Frontend: `http://localhost:4200`
   - Backend API: `http://127.0.0.1:8000/api/`
   - Admin: `http://127.0.0.1:8000/admin/`

## Next Steps

1. ✅ Add sample data through admin panel
2. ✅ Test all API endpoints
3. ✅ Test frontend-backend integration
4. ✅ Create sample questions, subjects, chapters
5. ✅ Test authentication flow

---

**Troubleshooting**: See `XAMPP_SETUP.md` for detailed troubleshooting guide.

