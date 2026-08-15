# Child Care backend (`bcheradip/childcare`)

Multi-functional preschool learning API for the **Child Care** Android app.

## Database

| Item | Value |
|------|--------|
| MySQL database | `childcare` |
| Django DB alias | `childcare` |
| Server app path | `/home/sasha/apps/cheradip/bcheradip/childcare` (with the rest of bcheradip) |
| Local | XAMPP `childcare` |

Included in `mysql_db_sync` via `DEFAULT_PROJECT_SYNC_DATABASES`.

### Create / migrate

```bash
# Local DB (already creatable via SQL or):
# mysql -u root -e "CREATE DATABASE IF NOT EXISTS childcare CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

cd D:\VSCode\cheradip\bcheradip
.\venv\Scripts\python manage.py migrate childcare --database=childcare
.\venv\Scripts\python manage.py seed_childcare_modules
```

### Sync local ↔ remote

```bash
.\venv\Scripts\python manage.py mysql_db_sync --l2r
# or only childcare:
# set SYNC_DATABASES=childcare in .env.db-sync for a one-off
```

On the remote host (if user cannot CREATE DATABASE):

```sql
CREATE DATABASE childcare CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON childcare.* TO 'sasha'@'localhost';
FLUSH PRIVILEGES;
```

## API (under `/api/childcare/`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/childcare/health/` | Health check |
| GET | `/api/childcare/dashboard/` | 15 dashboard modules |
| GET | `/api/childcare/modules/<key>/lessons/` | Lessons for a module |
| GET | `/api/childcare/shorts/` | Short videos |
| GET | `/api/childcare/friends/` | Friend characters |
| POST | `/api/childcare/auth/register/` | Register child (OTP next) |

## Dashboard module keys (1–15)

| # | key | Android icon |
|---|-----|--------------|
| 1 | friends | di_friends |
| 2 | arabic | di_arabic |
| 3 | bengali | di_bengali |
| 4 | english | di_english |
| 5 | math | di_math |
| 6 | iq | di_iq |
| 7 | animals | di_animals |
| 8 | fruits | di_fruits |
| 9 | vegetables | di_vegetables |
| 10 | human_body | di_hbody |
| 11 | drawing_pad | di_khata |
| 12 | quiz | di_quiz |
| 13 | games | di_games |
| 14 | shorts | di_shorts |
| 15 | contest | di_contest |
