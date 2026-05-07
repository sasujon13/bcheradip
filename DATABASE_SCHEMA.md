# Database Schema Documentation

## Overview
This document describes the complete database schema for the Cheradip project, including all tables, their relationships, data types, and constraints.

## Table of Contents
1. [E-Commerce Models](#e-commerce-models)
2. [User Management Models](#user-management-models)
3. [Educational Content Models](#educational-content-models)
4. [Notification Models](#notification-models)
5. [Job/Vacancy Models](#jobvacancy-models)
6. [Merit List Models](#merit-list-models)
7. [Recommendation Models](#recommendation-models)
8. [Institute Data Models](#institute-data-models)
9. [Utility Models](#utility-models)

---

## E-Commerce Models

### 1. `items`
Product/Item catalog for e-commerce functionality.

**Primary Key:** `id` (AutoField)

**Fields:**
- `id` - AutoField (Primary Key)
- `code` - CharField(4), Unique, Nullable, Indexed
- `name` - CharField(63), Nullable
- `bangla_name` - CharField(63), Nullable
- `size` - CharField(14), Choices: nctb, book, guide, cheradip
- `weight` - DecimalField(6,2), Nullable, MinValue=0
- `love` - BooleanField, Default=False
- `add_to_cart` - BooleanField, Default=False
- `in_stock` - IntegerField, Default=0, MinValue=0
- `price` - DecimalField(10,0), Nullable, MinValue=0
- `discount` - DecimalField(2,0), Default=0, MinValue=0
- `quantity` - IntegerField, Default=0, MinValue=0
- `image` - ImageField, Upload to 'images/items/'
- `videos` - URLField, Nullable
- `supplier` - CharField(54), Nullable
- `types` - CharField(15), Choices: science, business, humanities, compulsory, sac, ac, sc
- `reviews` - TextField, Nullable, Default="Rated By @Author"
- `ratings` - DecimalField(3,2), Default=5.00, MinValue=0
- `shipping` - TextField, Nullable, Default="NA"
- `payment_method` - CharField(28), Choices: cod, bkash, nagad, dbbl, other
- `details` - TextField, Nullable, Default="NA"
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated

**Indexes:**
- `code`
- `types`
- `name`

**Relationships:**
- One-to-Many: `OrderDetail.item`

---

### 2. `transactions`
Payment transactions for orders.

**Primary Key:** `id` (AutoField)

**Fields:**
- `id` - AutoField (Primary Key)
- `trxid` - CharField(31), Unique, Indexed
- `username` - CharField(11), Nullable, Indexed
- `paidFrom` - CharField(31), Default=''
- `Paid` - DecimalField(10,0), Nullable, MinValue=0
- `payment_method` - CharField(20), Choices: bkash, nagad, dbbl, rocket, cash
- `status` - CharField(20), Choices: pending, completed, failed, refunded
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated

**Indexes:**
- `trxid`
- `username`
- `status, created_at`

**Relationships:**
- Many-to-Many: `Order.transactions`, `Ordered.transactions`, `Canceled.transactions`

---

### 3. `order_details`
Individual line items in orders.

**Primary Key:** `id` (AutoField)

**Fields:**
- `id` - AutoField (Primary Key)
- `item` - ForeignKey(Item), Nullable, SET_NULL on delete
- `SN` - IntegerField, Default=0
- `Name` - CharField(127)
- `Image` - URLField, Nullable
- `Weight` - DecimalField(6,2), Nullable, MinValue=0
- `Price` - DecimalField(10,0), Nullable, MinValue=0
- `Quantity` - IntegerField, Default=1, MinValue=1
- `Discount` - DecimalField(9,0), Nullable, MinValue=0
- `Total` - DecimalField(10,0), Nullable, MinValue=0
- `GrandTotal` - DecimalField(10,0), Nullable, MinValue=0
- `Paid` - DecimalField(10,0), Nullable, MinValue=0
- `Due` - DecimalField(10,0), Nullable
- `ShipingCost` - DecimalField(8,0), Nullable, Default=0, MinValue=0
- `created_at` - DateTimeField, Auto-created

**Indexes:**
- `item`

**Relationships:**
- Foreign Key: `Item` (Many-to-One)
- Many-to-Many: `Order.orderDetails`, `Ordered.orderDetails`, `Canceled.orderDetails`

---

### 4. `orders`
Active/pending orders.

**Primary Key:** `id` (AutoField)

**Fields:**
- `id` - AutoField (Primary Key)
- `customer` - ForeignKey(Customer), Nullable, SET_NULL on delete
- `username` - CharField(11), Indexed
- `fullName` - CharField(31), Nullable
- `gender` - CharField(10), Nullable
- `altMobileNo` - CharField(11), Nullable
- `division` - CharField(31), Nullable
- `district` - CharField(31), Nullable
- `thana` - CharField(31), Nullable
- `union` - CharField(31), Nullable
- `village` - TextField(255), Nullable
- `paymentMethod` - CharField(31), Choices: cod, bkash, nagad, dbbl, other
- `status` - CharField(20), Choices: pending, processing, shipped, delivered, cancelled
- `shipped` - BooleanField, Default=False
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated

**Many-to-Many Fields:**
- `orderDetails` - Many-to-Many(OrderDetail)
- `transactions` - Many-to-Many(Transaction)

**Indexes:**
- `username`
- `status`
- `customer, created_at`

**Relationships:**
- Foreign Key: `Customer` (Many-to-One)
- Many-to-Many: `OrderDetail`, `Transaction`

---

### 5. `ordered`
Completed/delivered orders.

**Primary Key:** `id` (AutoField)

**Fields:** (Similar to `orders` but for completed orders)
- `id` - AutoField (Primary Key)
- `customer` - ForeignKey(Customer), Nullable, SET_NULL on delete
- `status` - CharField(20), Choices: shipped, delivered
- `delivered_at` - DateTimeField, Nullable

**Relationships:**
- Foreign Key: `Customer` (Many-to-One)
- Many-to-Many: `OrderDetail`, `Transaction`

---

### 6. `canceled`
Cancelled orders.

**Primary Key:** `id` (AutoField)

**Fields:** (Similar to `orders` but for cancelled orders)
- `cancellation_reason` - TextField, Nullable
- `cancelled_at` - DateTimeField, Auto-updated

**Relationships:**
- Foreign Key: `Customer` (Many-to-One)
- Many-to-Many: `OrderDetail`, `Transaction`

---

## User Management Models

### 7. `customers`
Custom user model for customers (extends AbstractBaseUser).

**Primary Key:** `id` (AutoField, inherited from AbstractBaseUser)

**Fields:**
- `id` - AutoField (Primary Key, inherited)
- `acctype` - CharField(7), Choices: Teacher, Student
- `username` - CharField(11), Unique, Indexed (USERNAME_FIELD)
- `password` - CharField(128) (handled by AbstractBaseUser)
- `fullName` - CharField(31)
- `group` - CharField(18), Choices: Science, Business Studies, Humanities
- `gender` - CharField(6), Choices: Male, Female, Common
- `division` - CharField(31)
- `district` - CharField(31)
- `thana` - CharField(31)
- `union` - CharField(31), Blank
- `village` - CharField(255)
- `email` - EmailField, Unique, Nullable
- `phone_alternate` - CharField(11), Nullable
- `is_active` - BooleanField, Default=True
- `is_staff` - BooleanField, Default=False
- `last_login` - DateTimeField (inherited from AbstractBaseUser)
- `date_joined` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated

**Many-to-Many Fields:**
- `groups` - Many-to-Many(AuthGroup)
- `user_permissions` - Many-to-Many(Permission)

**Indexes:**
- `username`
- `email`
- `acctype`
- `division, district`

**Relationships:**
- One-to-One: `CustomerToken.customer`
- One-to-Many: `Order.customer`, `Ordered.customer`, `Canceled.customer`

---

### 8. `customer_tokens`
Authentication tokens for customers.

**Primary Key:** `key` (CharField(40))

**Fields:**
- `key` - CharField(40), Primary Key
- `customer` - OneToOneField(Customer), CASCADE on delete
- `created` - DateTimeField, Default=timezone.now, Indexed
- `expires_at` - DateTimeField, Nullable

**Indexes:**
- `key`
- `customer, created`

**Relationships:**
- One-to-One: `Customer`

---

## Educational Content Models

### 9. `groups`
Educational groups (Science, Business, Humanities).

**Primary Key:** `group_code` (CharField(1))

**Fields:**
- `group_code` - CharField(1), Primary Key, Unique, Indexed
- `group_name` - CharField(50), Default=""
- `group_name_bn` - CharField(50), Nullable
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated

**Relationships:**
- Many-to-Many: `Subject.groups`

---

### 10. `subjects`
Subjects (e.g., ICT, Physics, Chemistry).

**Primary Key:** `subject_code` (CharField(3))

**Fields:**
- `subject_code` - CharField(3), Primary Key, Unique, Indexed
- `subject_name` - CharField(50), Blank
- `subject_name_bn` - CharField(50), Nullable
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated

**Many-to-Many Fields:**
- `groups` - Many-to-Many(Group), through table: `subject_groups`

**Relationships:**
- One-to-Many: `Chapter.subject`, `Mcq_ict.subject`

---

### 11. `chapters`
Chapters within subjects.

**Primary Key:** `id` (AutoField)

**Fields:**
- `id` - AutoField (Primary Key)
- `subject` - ForeignKey(Subject), CASCADE on delete, Indexed
- `chapter_no` - CharField(2), Blank, Indexed
- `chapter_name` - CharField(100), Blank
- `chapter_name_bn` - CharField(100), Nullable
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated

**Unique Constraints:**
- `(subject, chapter_no)` - Unique Together

**Indexes:**
- `subject, chapter_no`

**Relationships:**
- Foreign Key: `Subject` (Many-to-One)
- One-to-Many: `Topic.chapter`, `Mcq_ict.chapter`

---

### 12. `topics`
Topics within chapters.

**Primary Key:** `id` (AutoField)

**Fields:**
- `id` - AutoField (Primary Key)
- `chapter` - ForeignKey(Chapter), CASCADE on delete, Indexed
- `topic_no` - CharField(2), Blank, Indexed
- `topic_name` - CharField(100), Blank
- `topic_name_bn` - CharField(100), Nullable
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated

**Unique Constraints:**
- `(chapter, topic_no)` - Unique Together

**Indexes:**
- `chapter, topic_no`

**Relationships:**
- Foreign Key: `Chapter` (Many-to-One)
- One-to-Many: `Mcq_ict.topic`

---

### 13. `institutes`
Educational institutes (for questions).

**Primary Key:** `institute_code` (CharField(14))

**Fields:**
- `institute_code` - CharField(14), Primary Key, Unique, Indexed
- `institute_name` - CharField(127), Blank, Unique
- `institute_name_bn` - CharField(127), Nullable
- `institute_type` - CharField(127), Blank
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated

**Indexes:**
- `institute_code`
- `institute_name`
- `institute_type`

**Relationships:**
- Many-to-Many: `Mcq_ict.institutes`

---

### 14. `years`
Academic years.

**Primary Key:** `year_code` (CharField(5))

**Fields:**
- `year_code` - CharField(5), Primary Key, Unique, Indexed
- `year_name` - CharField(9), Blank, Unique
- `year_name_bn` - CharField(9), Nullable
- `start_year` - IntegerField, Nullable
- `end_year` - IntegerField, Nullable
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated

**Relationships:**
- Many-to-Many: `Mcq_ict.years`

---

### 15. `mcq_ict`
MCQ/ICT Questions.

**Primary Key:** `qid` (CharField(10))

**Fields:**
- `qid` - CharField(10), Primary Key, Unique, Editable=False, Indexed (Auto-generated)
- `subject` - ForeignKey(Subject), CASCADE on delete, Indexed
- `chapter` - ForeignKey(Chapter), CASCADE on delete, Indexed
- `topic` - ForeignKey(Topic), CASCADE on delete, Indexed
- `uddipok` - TextField(1000), Nullable (Question context/hint)
- `question` - TextField(300)
- `option1` - TextField(200)
- `option2` - TextField(200)
- `option3` - TextField(200)
- `option4` - TextField(200)
- `answer` - CharField(1), Choices: 1=ক, 2=খ, 3=গ, 4=ঘ
- `explanation` - TextField(1000), Nullable
- `img_uddipok` - ImageField, Upload to question_image_path, Nullable
- `img_question` - ImageField, Upload to question_image_path, Nullable
- `img_explanation` - ImageField, Upload to question_image_path, Nullable
- `difficulty_level` - CharField(20), Choices: easy, medium, hard
- `is_active` - BooleanField, Default=True
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated

**Many-to-Many Fields:**
- `institutes` - Many-to-Many(Institute), through table: `mcq_institutes`
- `years` - Many-to-Many(Year), through table: `mcq_years`

**Indexes:**
- `qid`
- `subject, chapter, topic`
- `is_active`
- `difficulty_level`

**Relationships:**
- Foreign Keys: `Subject`, `Chapter`, `Topic` (Many-to-One)
- Many-to-Many: `Institute`, `Year`

**QID Generation:** Format: `{subject_code}{chapter_no:02d}{topic_no:02d}{sequence:03d}`

---

## Notification Models

### 16. `notifications`
System notifications.

**Primary Key:** `id` (AutoField)

**Fields:**
- `id` - AutoField (Primary Key)
- `text` - TextField(1024), Nullable
- `link` - URLField(512), Nullable
- `title` - CharField(255), Nullable
- `is_active` - BooleanField, Default=True
- `priority` - IntegerField, Choices: 0=Normal, 1=High, 2=Urgent
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated
- `expires_at` - DateTimeField, Nullable

**Indexes:**
- `is_active, priority`
- `created_at`

---

## Job/Vacancy Models

### 17. `vacancies`
General teacher vacancies.

**Primary Key:** `VPID` (BigIntegerField)

**Fields:**
- `VPID` - BigIntegerField, Primary Key, Indexed
- `EIIN` - BigIntegerField, Indexed
- `Name` - CharField(255), Indexed
- `District` - CharField(255), Indexed
- `Thana` - CharField(255)
- `Designation` - CharField(255)
- `Subject` - CharField(255)
- `Vacancy` - IntegerField, Default=1, MinValue=1
- `Type` - CharField(15), Choices: regular, temporary, contract
- `Status` - CharField(31), Choices: open, closed, filled
- `description` - TextField, Nullable
- `salary_range` - CharField(100), Nullable
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated
- `deadline` - DateTimeField, Nullable

**Indexes:**
- `VPID`
- `EIIN`
- `Status, Type`
- `District, Thana`
- `Subject`

---

### 18. `vacancies_5`
Grade 5 teacher vacancies.

**Fields:** Similar to `vacancies` but for Grade 5 positions.

**Table:** `vacancies_5`

---

### 19. `vacancies_6`
Grade 6 teacher vacancies.

**Fields:** Similar to `vacancies` but for Grade 6 positions.

**Table:** `vacancies_6`

---

## Merit List Models

### 20. `merits`
General merit list positions.

**Primary Key:** `id` (AutoField)

**Fields:**
- `id` - AutoField (Primary Key)
- `Code` - IntegerField, Indexed
- `Name` - CharField(255), Indexed
- `Batch` - IntegerField, Indexed
- `Roll` - BigIntegerField, Indexed
- `Mark` - IntegerField
- `Rank` - IntegerField
- `SL` - IntegerField
- `Subject` - CharField(127), Indexed
- `EIIN` - BigIntegerField, Nullable, Indexed
- `InstituteName` - CharField(255), Nullable
- `created_at` - DateTimeField, Auto-created

**Unique Constraints:**
- `(Batch, Roll, Subject)` - Unique Together

**Indexes:**
- `Code`
- `Batch, Rank`
- `Roll`
- `Subject, Rank`
- `EIIN`

---

### 21. `merits_5`
Grade 5 merit list.

**Table:** `merits_5`
**Fields:** Similar to `merits` but for Grade 5.

**Unique Constraints:**
- `(Batch, Roll, Subject)` - Unique Together

---

### 22. `merits_6`
Grade 6 merit list.

**Table:** `merits_6`
**Fields:** Similar to `merits` but for Grade 6.

**Unique Constraints:**
- `(Batch, Roll, Subject)` - Unique Together

---

## Recommendation Models

### 23. `recommendations`
General teacher recommendations.

**Primary Key:** `id` (AutoField)

**Fields:**
- `id` - AutoField (Primary Key)
- `EIIN` - BigIntegerField, Indexed
- `District` - CharField(127), Nullable, Indexed
- `Thana` - CharField(127), Nullable
- `Designation` - CharField(255), Nullable
- `Post` - CharField(255), Nullable
- `Batch` - CharField(255), Nullable
- `Merit` - CharField(63), Nullable
- `Roll` - BigIntegerField, Nullable, Indexed
- `Name` - CharField(255), Nullable, Indexed
- `Code` - IntegerField, Nullable
- `Mark` - IntegerField, Nullable
- `Rank` - IntegerField, Nullable
- `Serial` - IntegerField, Nullable
- `Subject` - CharField(255), Nullable, Indexed
- `status` - CharField(50), Choices: pending, approved, rejected
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated

**Indexes:**
- `EIIN`
- `Roll`
- `Name`
- `Subject, Rank`
- `status`

---

### 24. `recommendations_5`
Grade 5 teacher recommendations.

**Table:** `recommendations_5`

---

### 25. `recommendations_6`
Grade 6 teacher recommendations.

**Table:** `recommendations_6`

---

## Institute Data Models

### 26. `banbeis`
BANBEIS (Bangladesh Bureau of Educational Information and Statistics) institute data.

**Primary Key:** `id` (AutoField)

**Fields:**
- `id` - AutoField (Primary Key)
- `EIIN` - BigIntegerField, Unique, Indexed
- `Name` - CharField(255), Nullable, Indexed
- `District` - CharField(255), Nullable, Indexed
- `Thana` - CharField(255), Nullable
- `Rejion` - CharField(255), Nullable (Note: Typo preserved from original)
- `PostOffice` - CharField(127), Nullable
- `PostCode` - CharField(7), Nullable
- `WardNo` - CharField(7), Nullable
- `Mouza` - CharField(127), Nullable
- `InstituteType` - CharField(127), Nullable, Indexed
- `EducationLevels` - CharField(255), Nullable
- `SSCDepts` - CharField(255), Nullable
- `HSCDepts` - CharField(255), Nullable
- `Linked` - TextField, Nullable
- `MPO` - CharField(255), Nullable
- `PreStats` - TextField, Nullable
- `Record` - TextField, Nullable
- `Record2` - TextField, Nullable
- `Contact` - CharField(255), Nullable
- `GovtStatus` - IntegerField, Choices: 0=Non-Government, 1=Government
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated

**Indexes:**
- `EIIN`
- `Name`
- `District, Thana`
- `InstituteType`
- `GovtStatus`

---

### 27. `institutes`
Detailed institute information.

**Primary Key:** `eiinNo` (CharField(15))

**Fields:**
- `eiinNo` - CharField(15), Primary Key, Indexed
- `id` - IntegerField, Nullable
- `instituteName` - CharField(255), Nullable, Indexed
- `instituteNameBn` - CharField(255), Nullable
- `mobile` - CharField(15), Nullable
- `mobileAlternate` - CharField(15), Nullable
- `email` - CharField(100), Nullable, Indexed
- `year` - IntegerField, Nullable
- `divisionName` - CharField(100), Nullable, Indexed
- `divisionNameBn` - CharField(100), Nullable
- `districtName` - CharField(100), Nullable, Indexed
- `districtNameBn` - CharField(100), Nullable
- `thanaName` - CharField(100), Nullable, Indexed
- `thanaNameBn` - CharField(100), Nullable
- `mouzaName` - CharField(255), Nullable
- `mouzaNameBn` - CharField(255), Nullable
- `instituteTypeName` - CharField(100), Nullable, Indexed
- `instituteTypeNameBn` - CharField(100), Nullable
- `isGovt` - BooleanField, Nullable, Default=False
- `submissionDate` - DateField, Nullable
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated

**Indexes:**
- `eiinNo`
- `instituteName`
- `divisionName, districtName, thanaName`
- `instituteTypeName`
- `isGovt`

---

## Utility Models

### 28. `tokens`
Token storage for various operations.

**Primary Key:** `id` (AutoField)

**Fields:**
- `id` - AutoField (Primary Key)
- `Token` - BigIntegerField, Unique, Indexed
- `Counter` - CharField(255), Nullable
- `Status` - IntegerField, Choices: 0=Inactive, 1=Active, 2=Used, 3=Expired
- `purpose` - CharField(50), Nullable, Indexed
- `expires_at` - DateTimeField, Nullable
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated

**Indexes:**
- `Token`
- `Status`
- `purpose`

---

### 29. `json_data`
Flexible JSON data storage.

**Primary Key:** `id` (AutoField)

**Fields:**
- `id` - AutoField (Primary Key)
- `data` - JSONField
- `data_type` - CharField(50), Nullable, Indexed
- `description` - CharField(255), Nullable
- `created_at` - DateTimeField, Auto-created
- `updated_at` - DateTimeField, Auto-updated

**Indexes:**
- `data_type`
- `created_at`

---

## Key Improvements Made

### 1. **Data Type Fixes**
- Fixed `BigIntegerField(max_length=...)` issues - removed invalid `max_length` parameter
- Added proper validators (MinValueValidator) for numeric fields
- Standardized null/blank configurations

### 2. **Primary Keys**
- All tables have explicit primary keys
- Composite unique constraints where appropriate (Chapter, Topic, Merit models)
- Proper AutoField usage

### 3. **Foreign Keys & Relationships**
- Added proper `on_delete` behaviors (CASCADE, SET_NULL)
- Added `related_name` for reverse relationships
- Improved Many-to-Many relationships with explicit through tables where needed
- Added ForeignKey from Order to Customer for better data integrity

### 4. **Indexes**
- Strategic indexes on frequently queried fields
- Composite indexes for common query patterns
- Indexes on foreign keys

### 5. **Meta Classes**
- Added `db_table` names for all models
- Proper `ordering` for default querysets
- Comprehensive index definitions
- `unique_together` constraints where needed

### 6. **Timestamps**
- Added `created_at` and `updated_at` fields to all models
- Special timestamps where appropriate (delivered_at, cancelled_at, expires_at)

### 7. **Data Integrity**
- Added field choices for status/enum fields
- Default values where appropriate
- Proper null handling

### 8. **Code Quality**
- Better field naming consistency
- Added help text where appropriate
- Improved docstrings
- Organized models into logical sections

---

## Migration Notes

When applying these changes:

1. **Backup existing data** before running migrations
2. Run: `python manage.py makemigrations`
3. Review migration files for any data migration needs
4. Run: `python manage.py migrate`
5. Update `AUTH_USER_MODEL` in settings.py if using Customer as user model:
   ```python
   AUTH_USER_MODEL = 'cheradip.Customer'
   ```

---

## Database Relationships Diagram

```
Customer (1) ────────< (N) Order
                      ├───< (N) Ordered
                      └───< (N) Canceled

Customer (1) ────────< (1) CustomerToken

Group (N) ────< M2M >─── (N) Subject
                               ├───< (N) Chapter
                               │       └───< (N) Topic
                               │               └───< (N) Mcq_ict
                               └───< (N) Mcq_ict

Mcq_ict (N) ────< M2M >─── (N) Institute
Mcq_ict (N) ────< M2M >─── (N) Year

Item (1) ────────< (N) OrderDetail
                    └───< M2M >─── (N) Order
                    └───< M2M >─── (N) Ordered
                    └───< M2M >─── (N) Canceled

Transaction (N) ────< M2M >─── (N) Order
                     └───< M2M >─── (N) Ordered
                     └───< M2M >─── (N) Canceled
```

---

## Summary Statistics

- **Total Models:** 29
- **E-Commerce Models:** 6
- **User Management Models:** 2
- **Educational Content Models:** 7
- **Notification Models:** 1
- **Job/Vacancy Models:** 3
- **Merit List Models:** 3
- **Recommendation Models:** 3
- **Institute Data Models:** 2
- **Utility Models:** 2

All tables are properly structured with appropriate data types, keys, relationships, indexes, and constraints following Django best practices.

