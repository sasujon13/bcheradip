-- Child Care database bootstrap (MySQL 8+ / MariaDB)
-- Database name: childcare
-- Hosting path companion: bcheradip/childcare (Django services)

CREATE DATABASE IF NOT EXISTS childcare
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE childcare;

-- Tables are normally created by Django migrations:
--   python manage.py migrate childcare --database=childcare
-- This file documents the intended schema and can seed modules after migrate.

INSERT INTO cc_modules (key, title_en, title_bn, icon_name, sort_order, is_enabled, description)
VALUES
  ('friends', 'Friends', 'বন্ধু', 'di_friends', 1, 1, 'Companion characters / social greetings'),
  ('arabic', 'Arabic', 'আরবি', 'di_arabic', 2, 1, 'Arabic alphabet learning'),
  ('bengali', 'Bengali', 'বাংলা', 'di_bengali', 3, 1, 'Bengali alphabet learning'),
  ('english', 'English', 'ইংরেজি', 'di_english', 4, 1, 'Letters, numbers, signs, quiz'),
  ('math', 'Math', 'গণিত', 'di_math', 5, 1, 'Counting and basic arithmetic'),
  ('iq', 'IQ', 'বুদ্ধিমত্তা', 'di_iq', 6, 1, 'Puzzles and pattern games'),
  ('animals', 'Animals', 'প্রাণী', 'di_animals', 7, 1, 'Animal cards and sounds'),
  ('fruits', 'Fruits', 'ফলমূল', 'di_fruits', 8, 1, 'Fruit cards'),
  ('vegetables', 'Vegetables', 'সবজি', 'di_vegetables', 9, 1, 'Vegetable cards'),
  ('human_body', 'Human Body', 'মানব দেহ', 'di_hbody', 10, 1, 'Body parts'),
  ('drawing_pad', 'Drawing Pad', 'খাতা', 'di_khata', 11, 1, 'Drawing canvas'),
  ('quiz', 'Quiz', 'কুইজ', 'di_quiz', 12, 1, 'Cross-module quiz hub'),
  ('games', 'Games', 'খেলা', 'di_games', 13, 1, 'Offline mini games'),
  ('shorts', 'Shorts', 'শর্টস', 'di_shorts', 14, 1, 'Short educational videos'),
  ('contest', 'Contest', 'প্রতিযোগিতা', 'di_contest', 15, 1, 'Challenges and leaderboard')
ON DUPLICATE KEY UPDATE
  title_en = VALUES(title_en),
  title_bn = VALUES(title_bn),
  icon_name = VALUES(icon_name),
  sort_order = VALUES(sort_order),
  is_enabled = VALUES(is_enabled);
