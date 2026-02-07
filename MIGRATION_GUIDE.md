# Database Migration Guide

## Overview
This guide provides step-by-step instructions for migrating your database schema to the updated models structure with proper data types, keys, and relationships.

## Important Notes

⚠️ **CRITICAL:** Before running migrations:
1. **BACKUP YOUR DATABASE** - Always backup your existing database before running migrations
2. **BACKUP YOUR CODE** - Commit your current code to version control
3. **TEST IN DEVELOPMENT** - Test all migrations in a development environment first

---

## Pre-Migration Checklist

- [ ] Database backup completed
- [ ] Code committed to version control
- [ ] Django virtual environment activated
- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] Database connection configured in `settings.py`
- [ ] `AUTH_USER_MODEL` set in `settings.py` (see below)

---

## Step 1: Update Settings Configuration

### 1.1 Verify AUTH_USER_MODEL Setting

The `settings.py` file has been updated to include:

```python
AUTH_USER_MODEL = 'cheradip.Customer'
```

If this is a **NEW** installation, you're good to go. 

If this is an **EXISTING** installation with existing user data, you need to:

1. **Check if you have existing User records:**
   ```bash
   python manage.py shell
   >>> from django.contrib.auth.models import User
   >>> User.objects.count()
   ```

2. **If you have existing users, you have two options:**

   **Option A: Migrate existing User data to Customer model**
   - Create a data migration script to copy data from `auth_user` to `customers` table
   - This is complex and requires careful data mapping

   **Option B: Keep using Django's default User model**
   - Remove `AUTH_USER_MODEL` from settings.py
   - Modify Customer model to not extend AbstractBaseUser
   - Use a OneToOne relationship instead

   **⚠️ Recommendation:** If you're early in development or can afford data loss, Option B with a fresh start is safer.

---

## Step 2: Create Migration Files

### 2.1 Activate Virtual Environment

```bash
cd bcheradip
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

### 2.2 Make Migrations

```bash
python manage.py makemigrations cheradip
```

This will:
- Detect all model changes
- Create migration files in `cheradip/migrations/`
- Show you what changes will be made

### 2.3 Review Migration Files

**Important:** Review the generated migration files before applying them:

```bash
# View the latest migration file
python manage.py showmigrations cheradip

# View migration SQL (optional)
python manage.py sqlmigrate cheradip <migration_number>
```

**Check for:**
- Field type changes that might cause data loss
- Removed fields or models
- Changed relationships
- New required fields without defaults

---

## Step 3: Handle Data Migration (If Needed)

### 3.1 Common Migration Scenarios

#### Scenario A: Empty Database (New Installation)
✅ **Easiest path** - Just run migrations:
```bash
python manage.py migrate
```

#### Scenario B: Existing Database with Data

**3.2.1 BigIntegerField Issues**
If you had models with `BigIntegerField(max_length=...)` (which is invalid), Django will try to fix this. The migration should handle it automatically.

**3.2.2 New Required Fields**
If any model now has required fields that didn't exist before, you'll need to:

1. Create a data migration:
   ```bash
   python manage.py makemigrations cheradip --empty --name populate_new_fields
   ```

2. Edit the migration file to set default values for existing records

**3.2.3 Changed Relationships**
- Foreign keys that changed from nullable to required
- Many-to-many relationships that were restructured

**Example:** If `Order.customer` is now a ForeignKey but wasn't before:
```python
# In data migration
from django.db import migrations

def populate_customer_fk(apps, schema_editor):
    Order = apps.get_model('cheradip', 'Order')
    Customer = apps.get_model('cheradip', 'Customer')
    
    for order in Order.objects.filter(customer__isnull=True):
        # Try to find customer by username
        try:
            customer = Customer.objects.get(username=order.username)
            order.customer = customer
            order.save()
        except Customer.DoesNotExist:
            # Handle case where customer doesn't exist
            # Create one or skip
            pass

class Migration(migrations.Migration):
    dependencies = [
        ('cheradip', 'xxxx_previous_migration'),
    ]
    
    operations = [
        migrations.RunPython(populate_customer_fk),
    ]
```

---

## Step 4: Run Migrations

### 4.1 Dry Run (Optional - PostgreSQL only)

PostgreSQL supports transaction rollback for testing:
```bash
# This won't work with MySQL/SQLite
python manage.py migrate --fake-initial
```

### 4.2 Apply Migrations

```bash
python manage.py migrate cheradip
```

Or migrate all apps:
```bash
python manage.py migrate
```

### 4.3 If Migration Fails

**Common Issues:**

1. **"Table already exists"**
   ```bash
   python manage.py migrate --fake-initial
   ```

2. **"Field cannot be null"**
   - Create a data migration to populate null values
   - Or temporarily allow null, populate data, then make required

3. **"Foreign key constraint fails"**
   - Check for orphaned records
   - Fix data integrity issues first

4. **"Duplicate entry"**
   - Remove duplicate records or fix unique constraints

---

## Step 5: Verify Migration Success

### 5.1 Check Migration Status

```bash
python manage.py showmigrations
```

All migrations should show `[X]` (applied).

### 5.2 Verify Tables

```bash
python manage.py shell
```

```python
from django.db import connection
cursor = connection.cursor()
cursor.execute("SHOW TABLES")
tables = [row[0] for row in cursor.fetchall()]
print("\n".join(sorted(tables)))
```

**Expected Tables (29 total):**
- items
- transactions
- order_details
- orders
- ordered
- canceled
- customers
- customer_tokens
- json_data
- groups
- subjects
- subject_groups (M2M table)
- chapters
- topics
- institutes
- years
- mcq_ict
- mcq_institutes (M2M table)
- mcq_years (M2M table)
- notifications
- vacancies
- vacancies_5
- vacancies_6
- merits
- merits_5
- merits_6
- recommendations
- recommendations_5
- recommendations_6
- banbeis
- tokens

### 5.3 Test Model Access

```python
from cheradip.models import *
# Test imports
Item.objects.all()
Customer.objects.all()
Mcq_ict.objects.all()
# etc.
```

### 5.4 Test Admin Interface

```bash
python manage.py runserver
```

Visit: http://127.0.0.1:8000/admin

Verify:
- All models are accessible
- No errors when viewing model lists
- Can create/edit/delete records

---

## Step 6: Create Superuser (If New Installation)

If this is a fresh installation:

```bash
python manage.py createsuperuser
```

**Note:** Since we're using a custom user model (`Customer`), the `createsuperuser` command will use `CustomerManager`.

You'll be prompted for:
- Username (mobile number - 11 digits)
- Password
- Full Name
- Other required fields

---

## Step 7: Verify Application Functionality

### 7.1 Test API Endpoints

If you have REST API endpoints, test them:

```bash
# Example: Test customer endpoint
curl http://127.0.0.1:8000/api/customers/
```

### 7.2 Test Serializers

```python
python manage.py shell
from cheradip.models import Item, Customer
from cheradip.serializers import ItemSerializer

item = Item.objects.first()
serializer = ItemSerializer(item)
print(serializer.data)
```

### 7.3 Test Views

Run your test suite if you have one:
```bash
python manage.py test
```

---

## Rollback Instructions

### If Migration Fails and You Need to Rollback:

**Option 1: Rollback Last Migration**
```bash
python manage.py migrate cheradip <previous_migration_number>
```

**Option 2: Rollback All Migrations (DESTRUCTIVE)**
```bash
python manage.py migrate cheradip zero
```

**⚠️ Warning:** This will delete all tables! Only use if you have a backup.

**Option 3: Restore from Backup**
1. Drop current database
2. Create new database
3. Restore from backup
4. Fix issues in code
5. Retry migration

---

## Post-Migration Tasks

### 1. Update Serializers (If Needed)

Check if serializers need updates for new fields:
```python
# Example: Add new fields to serializer
class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = '__all__'  # This includes all fields automatically
        # Or explicitly list fields if needed
```

### 2. Update Views (If Needed)

Views should work automatically if using ModelViewSet, but check:
- Custom querysets
- Filtering by new fields
- Ordering by new fields

### 3. Update Frontend

If your Angular frontend (fcheradip) expects specific fields:
- Update TypeScript interfaces
- Update API service methods
- Test all CRUD operations

### 4. Update Documentation

- Update API documentation
- Update frontend component documentation
- Document any breaking changes

---

## Common Issues and Solutions

### Issue 1: "No such table: django_migrations"

**Solution:**
```bash
python manage.py migrate --run-syncdb
```

### Issue 2: "Field 'id' cannot be null" 

**Cause:** Model had explicit `id` field that was removed or changed

**Solution:**
- Let Django handle AutoField automatically
- Remove explicit `id = models.AutoField(primary_key=True)` if it conflicts

### Issue 3: "IntegrityError: foreign key constraint fails"

**Cause:** Orphaned records or invalid foreign key references

**Solution:**
```python
# Find orphaned records
Order.objects.filter(customer__isnull=True)

# Fix them
for order in Order.objects.filter(customer__isnull=True):
    customer = Customer.objects.get(username=order.username)
    order.customer = customer
    order.save()
```

### Issue 4: "django.db.utils.OperationalError: (1091, "Can't DROP INDEX...")"

**Cause:** Index doesn't exist but migration tries to drop it

**Solution:**
```bash
# Fake the migration that adds the index
python manage.py migrate cheradip <migration_number> --fake
```

### Issue 5: MySQL "Incorrect string value" for emoji/unicode

**Solution:**
Ensure database uses `utf8mb4` charset (already configured in settings.py):
```python
'OPTIONS': {
    'charset': 'utf8mb4',
}
```

---

## Database-Specific Notes

### MySQL
- Already configured with `utf8mb4` charset
- Uses `pymysql` adapter
- Foreign key checks are enabled

### PostgreSQL
- Better for complex queries
- Supports partial indexes
- Better transaction handling

### SQLite (Development only)
- Auto-increment issues with composite keys
- Limited ALTER TABLE support
- Not recommended for production

---

## Performance Optimization

After migration, consider:

1. **Add Database Indexes** (already added in models, but verify):
   ```sql
   SHOW INDEX FROM items;
   ```

2. **Analyze Tables** (MySQL):
   ```sql
   ANALYZE TABLE items, customers, mcq_ict;
   ```

3. **Optimize Tables** (MySQL):
   ```sql
   OPTIMIZE TABLE items, customers, mcq_ict;
   ```

---

## Success Criteria

✅ All migrations applied successfully  
✅ All 29 tables created  
✅ No foreign key constraint errors  
✅ Admin interface accessible  
✅ API endpoints working  
✅ No data loss (if existing database)  
✅ All models can be imported  
✅ Can create/edit/delete records  

---

## Support

If you encounter issues:

1. Check Django migration documentation: https://docs.djangoproject.com/en/stable/topics/migrations/
2. Check error logs: `debug.log`
3. Use Django shell to debug: `python manage.py shell`
4. Check database directly: `mysql -u root -p cheradip_cheradip`

---

## Quick Reference Commands

```bash
# Make migrations
python manage.py makemigrations cheradip

# Show migrations
python manage.py showmigrations

# Apply migrations
python manage.py migrate cheradip

# Rollback
python manage.py migrate cheradip <previous_number>

# Fake migration (mark as done without running)
python manage.py migrate cheradip <number> --fake

# Show SQL for migration
python manage.py sqlmigrate cheradip <number>

# Create superuser
python manage.py createsuperuser

# Open Django shell
python manage.py shell

# Run tests
python manage.py test
```

---

**Last Updated:** 2024
**Django Version:** 4.x+
**Python Version:** 3.8+

