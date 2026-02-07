# Environment Setup Guide for Cheradip Backend

## Overview
This guide explains how to set up the environment variables and configure the Django backend for the Cheradip project.

## Prerequisites
- Python 3.8 or higher
- MySQL database server
- Virtual environment (recommended)

## Installation Steps

### 1. Install Dependencies
```bash
cd bcheradip
pip install -r requirements.txt
```

### 2. Environment Variables Setup

Create a `.env` file in the `bcheradip` directory (same level as `manage.py`):

```bash
# Django Settings
SECRET_KEY=your-secret-key-here-change-this-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,cheradip.com

# Database Configuration
DATABASE_NAME=cheradip_cheradip
DATABASE_USER=cheradip_cheradip
DATABASE_PASSWORD=your-database-password-here
DATABASE_HOST=cheradip.com
DATABASE_PORT=3306

# Media & Static
HOST_URL=http://127.0.0.1:8000
# HOST_URL=https://cheradip.com  # For production

# CORS Settings
CORS_ALLOWED_ORIGINS=http://localhost:4200,https://cheradip.com
CORS_ORIGIN_ALLOW_ALL=False
```

### 3. Generate Secret Key
To generate a secure SECRET_KEY, you can use:
```python
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

Or use an online Django secret key generator.

### 4. Database Migration
```bash
python manage.py makemigrations
python manage.py migrate
```

### 5. Create Superuser
```bash
python manage.py createsuperuser
```

### 6. Run Development Server
```bash
python manage.py runserver
```

## Security Improvements Implemented

### ✅ Environment Variables
- All sensitive data (SECRET_KEY, database credentials) are now stored in `.env` file
- `.env` file is excluded from version control via `.gitignore`

### ✅ Password Security
- Passwords are now hashed using Django's built-in password hashing
- Legacy plain text passwords are automatically migrated to hashed passwords on login
- Custom authentication backend handles both hashed and legacy passwords during migration period

### ✅ CORS Configuration
- CORS origins are configurable via environment variables
- `CORS_ORIGIN_ALLOW_ALL` is set to `False` by default (more secure)
- Specific allowed origins can be configured in `.env`

### ✅ Database Configuration
- Database credentials are stored in environment variables
- Connection options optimized for MySQL with UTF-8 support

## API Endpoints Available

### MCQ Question Management
- `GET /api/questions/` - List all questions (with filtering)
- `POST /api/questions/` - Create new question
- `GET /api/questions/{qid}/` - Get specific question
- `PUT /api/questions/{qid}/` - Update question
- `PATCH /api/questions/{qid}/` - Partial update
- `DELETE /api/questions/{qid}/` - Delete question
- `GET /api/questions/statistics/` - Get question statistics

### Question Filtering Parameters
- `?subject=101&subject=102` - Filter by subject codes
- `?chapter=01&chapter=02` - Filter by chapter numbers
- `?topic=01&topic=02` - Filter by topic numbers
- `?institute=INST001&institute=INST002` - Filter by institute codes
- `?year=2024&year=2023` - Filter by year codes
- `?group=S&group=A` - Filter by group codes
- `?search=question text` - Search in question text, options, explanation
- `?qid=10101001` - Get specific question by ID

### Related Endpoints
- `GET /api/subjects/` - List all subjects
  - `?groups=S,A,B` - Filter by group codes
  - `?subject_code=101` - Get specific subject

- `GET /api/chapters/` - List all chapters
  - `?subjects=101,102` - Filter by subject codes
  - `?chapter_no=01` - Filter by chapter number

- `GET /api/topics/` - List all topics
  - `?chapters=1,2,3` - Filter by chapter IDs
  - `?topic_no=01` - Filter by topic number

- `GET /api/groups/` - List all groups
  - `?group_code=S` - Get specific group

- `GET /api/instituteTypes/` - List all institutes
  - `?institute_code=INST001` - Get specific institute
  - `?institute_type=Type1&institute_type=Type2` - Filter by types

- `GET /api/years/` - List all years
  - `?year_code=2024` - Get specific year
  - `?institutes=INST001,INST002` - Filter by institutes

## Authentication Endpoints

- `POST /api/signup/` - Create new customer account
- `POST /api/login/` - Login (returns authToken)
- `POST /api/profile_update/` - Update customer profile
- `POST /api/password_update/` - Update password
- `POST /api/mobile_update/` - Update mobile number
- `GET /api/username/?username=01712345678` - Check if username exists
- `GET /api/password/?username=01712345678&password=pass` - Verify password

## Password Migration

The system supports automatic password migration:
- **New users**: Passwords are automatically hashed on signup
- **Existing users**: Plain text passwords are checked on login and automatically migrated to hashed passwords
- **Password updates**: All password updates use hashed storage

This ensures backward compatibility while improving security.

## Production Deployment

### Important Production Settings

1. **Set DEBUG=False**:
   ```env
   DEBUG=False
   ```

2. **Update ALLOWED_HOSTS**:
   ```env
   ALLOWED_HOSTS=cheradip.com,www.cheradip.com
   ```

3. **Use Strong SECRET_KEY**:
   ```env
   SECRET_KEY=<generate-a-strong-random-key>
   ```

4. **Update HOST_URL**:
   ```env
   HOST_URL=https://cheradip.com
   ```

5. **Configure CORS properly**:
   ```env
   CORS_ALLOWED_ORIGINS=https://cheradip.com,https://www.cheradip.com
   CORS_ORIGIN_ALLOW_ALL=False
   ```

6. **Set up Static Files**:
   ```bash
   python manage.py collectstatic
   ```

## Troubleshooting

### Issue: ModuleNotFoundError: No module named 'decouple'
**Solution**: Install python-decouple
```bash
pip install python-decouple
```

### Issue: Database connection error
**Solution**: Check your `.env` file database configuration matches your MySQL setup.

### Issue: CORS errors in frontend
**Solution**: 
1. Check `CORS_ALLOWED_ORIGINS` in `.env` includes your frontend URL
2. Ensure `CORS_ORIGIN_ALLOW_ALL=False` (more secure)

### Issue: Password authentication not working
**Solution**: 
- If you have existing plain text passwords, they will be automatically migrated on next login
- New users will have hashed passwords automatically
- Check that `CustomBackend` is in `AUTHENTICATION_BACKENDS` in settings.py

## Notes

- The `.env` file should never be committed to version control
- Always use different SECRET_KEY for production
- Keep database credentials secure
- Regularly update dependencies for security patches

