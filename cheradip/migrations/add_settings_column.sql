-- Add missing 'settings' column to cheradip_customers (fixes signup 500: Unknown column 'settings')
-- Run this if you cannot use: python manage.py migrate
-- MySQL/MariaDB:
ALTER TABLE cheradip_customers ADD COLUMN settings JSON NULL;
