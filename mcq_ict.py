import os
import sys
import django

sys.path.append('E:/Running/cheradip/bcheradip')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

import csv
from cheradip.models import Subject, Chapter, Topic, Mcq_ict, Institute, Year

csv_file_path = 'C:\\Users\\sasha\\Desktop\\cheradip_database_mcq.csv'

with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    
    for row in reader:
        subject_code = row['subject_code']
        chapter_no = row['chapter_no']
        topic_no = row['topic_no']
        question = row['question']
        option1 = row['option1']
        option2 = row['option2']
        option3 = row['option3']
        option4 = row['option4']
        answer = row['answer']
        explanation = row['explanation']
        img_uddipok = row['img_uddipok'] if 'img_uddipok' in row else None
        img_question = row['img_question'] if 'img_question' in row else None
        img_explanation = row['img_explanation'] if 'img_explanation' in row else None
        year_institute_data = row['year_institute']  # Example: "DiB '23, SB '19"
        
        try:
            subject = Subject.objects.get(subject_code=subject_code)
            chapter = Chapter.objects.get(subject=subject, chapter_no=chapter_no)
            topic = Topic.objects.get(chapter=chapter, topic_no=topic_no)
            
            mcq, created = Mcq_ict.objects.update_or_create(
                subject=subject,
                chapter=chapter,
                topic=topic,
                question=question,
                defaults={
                    'option1': option1,
                    'option2': option2,
                    'option3': option3,
                    'option4': option4,
                    'answer': answer,
                    'explanation': explanation,
                    'img_uddipok': img_uddipok
                    'img_question': img_question
                    'img_explanation': img_explanation
                }
            )

            # Clear current institutes and years, if necessary
            mcq.institutes.clear()
            mcq.years.clear()

            # Parsing and assigning institutes and years
            year_institute_pairs = year_institute_data.split(', ')
            for pair in year_institute_pairs:
                institute_code, year = pair.split(" '")
                institute = Institute.objects.get(institute_code=institute_code.strip())
                year_code, _ = Year.objects.get_or_create(year=int(year.strip()))

                # Add to ManyToMany relationships
                mcq.institute.add(institute)
                mcq.year.add(year_code)

            mcq.save()

            if created:
                print(f"Inserted new MCQ for {subject_code} - Chapter {chapter_no}")
            else:
                print(f"Updated existing MCQ for {subject_code} - Chapter {chapter_no}")
        
        except Subject.DoesNotExist:
            print(f"Subject with code {subject_code} does not exist")
        except Chapter.DoesNotExist:
            print(f"Chapter {chapter_no} for subject {subject_code} does not exist")
        except Topic.DoesNotExist:
            print(f"Topic {topic_no} for chapter {chapter_no} does not exist")
        except Institute.DoesNotExist:
            print(f"Institute with code {institute_code} does not exist")
