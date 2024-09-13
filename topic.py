
import os
import sys
import django

sys.path.append('E:/Running/cheradip/bcheradip')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

import csv
from cheradip.models import Subject, Chapter, Topic

csv_file_path = 'C:\\Users\\sasha\\Desktop\\cheradip_database - Topic__Inserted.csv'

with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    
    for row in reader:
        subject_code = row['subject_code']
        chapter_no = row['chapter_no']
        topic_no = row['topic_no']
        topic_name = row['topic_name']
        
        try:
            subject = Subject.objects.get(subject_code=subject_code)
            chapter = Chapter.objects.get(subject=subject, chapter_no=chapter_no)
            topic, created = Topic.objects.update_or_create(
                chapter=chapter,
                topic_no=topic_no,
                defaults={'topic_name': topic_name}
            )
            if created:
                print(f"Inserted!")
            else:
                print(f"Updated!")
        
        except Subject.DoesNotExist:
            print(f"Subject with code {subject_code} does not exist")
        except Chapter.DoesNotExist:
            print(f"Chapter {chapter_no} for subject {subject_code} does not exist")
