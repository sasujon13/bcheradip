-- Run in phpMyAdmin or: mysql -u root < sql/01_create_database.sql
CREATE DATABASE IF NOT EXISTS ailanguagetutor
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE ailanguagetutor;

-- Tables are created automatically by the API on first start (SQLAlchemy).
-- This file only creates the database name for XAMPP.
