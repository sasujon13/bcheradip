import os
import sys
import django

sys.path.append('E:/Running/cheradip/bcheradip')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

import csv
from cheradip.models import Subject, Chapter, Topic, Mcq_ict, Institute, Year

csv_file_path = 'C:\\Users\\sasha\\Desktop\\mcq_ict.csv'

answer_mapping = {
    '1': 'ক',
    '2': 'খ',
    '3': 'গ',
    '4': 'ঘ'
}

with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    
    for row in reader:
        subject_code = row['subject_code']
        chapter_no = row['chapter_no']
        topic_no = row['topic_no']
        uddipok = row['uddipok']
        question = row['question']
        option1 = row['option1']
        option2 = row['option2']
        option3 = row['option3']
        option4 = row['option4']
        answer = row['answer']
        mapped_answer = answer_mapping.get(answer, answer)
        explanation = row['explanation']
        img_uddipok = row.get('img_uddipok')
        img_question = row.get('img_question')
        img_explanation = row.get('img_explanation')
        year_institute_data = row['year_institute']  # Example: "DiB '23, SB '19, MARS"

        try:
            # Fetch subject, chapter, and topic
            subject = Subject.objects.get(subject_code=subject_code)
            chapter = Chapter.objects.get(subject=subject, chapter_no=chapter_no)
            topic = Topic.objects.get(chapter=chapter, topic_no=topic_no)
            
            # Update or create the MCQ entry
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
                    'answer': mapped_answer,
                    'uddipok': uddipok,
                    'explanation': explanation,
                    'img_uddipok': img_uddipok,
                    'img_question': img_question,
                    'img_explanation': img_explanation
                }
            )

            # Clear current institutes and years
            mcq.institutes.clear()
            mcq.years.clear()

            # Parsing and assigning institutes and years
            year_institute_pairs = year_institute_data.split(', ')
            for pair in year_institute_pairs:
                if " '" in pair:
                    # Case where both institute and year are present (e.g., "DiB '23")
                    parts = pair.split(" '")
                    institute_code = parts[0].strip()
                    year = parts[1].strip()

                    # Debugging output to verify the parsed values
                    print(f"Processing: Institute Code={institute_code}, Year={year}")

                    try:
                        institute = Institute.objects.get(institute_code=institute_code)
                        year_code = Year.objects.get(year_code=year)

                        # Add to ManyToMany relationships
                        mcq.institutes.add(institute)
                        mcq.years.add(year_code)

                    except Institute.DoesNotExist:
                        print(f"Institute with code '{institute_code}' does not exist.")
                    except Year.DoesNotExist:
                        print(f"Year with code '{year}' does not exist.")

                else:
                    # Case where only institute is present (e.g., "MARS")
                    institute_code = pair.strip()

                    # Debugging output to verify the parsed values
                    print(f"Processing: Institute Code={institute_code} (no year)")

                    try:
                        institute = Institute.objects.get(institute_code=institute_code)

                        # Add the institute to the ManyToMany relationship
                        mcq.institutes.add(institute)

                    except Institute.DoesNotExist:
                        print(f"Institute with code '{institute_code}' does not exist.")

            mcq.save()  # Ensure MCQ is saved after updates

            if created:
                print(f"Inserted new MCQ for {subject_code} - Chapter {chapter_no}")
            else:
                print(f"Updated existing MCQ for {subject_code} - Chapter {chapter_no}")

        except Subject.DoesNotExist:
            print(f"Subject with code '{subject_code}' does not exist")
        except Chapter.DoesNotExist:
            print(f"Chapter {chapter_no} for subject {subject_code} does not exist")
        except Topic.DoesNotExist:
            print(f"Topic {topic_no} for chapter {chapter_no} does not exist")



# import os
# import sys
# import django

# sys.path.append('E:/Running/cheradip/bcheradip')
# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
# django.setup()

# import csv
# from cheradip.models import Subject, Chapter, Topic, Mcq_ict, Institute, Year

# csv_file_path = 'C:\\Users\\sasha\\Desktop\\mcq_ict.csv'

# answer_mapping = {
#     '1': 'ক',
#     '2': 'খ',
#     '3': 'গ',
#     '4': 'ঘ'
# }

# with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
#     reader = csv.DictReader(csvfile)
    
#     for row in reader:
#         subject_code = row['subject_code']
#         chapter_no = row['chapter_no']
#         topic_no = row['topic_no']
#         uddipok = row['uddipok']
#         question = row['question']
#         option1 = row['option1']
#         option2 = row['option2']
#         option3 = row['option3']
#         option4 = row['option4']
#         answer = row['answer']
#         mapped_answer = answer_mapping.get(answer, answer)
#         explanation = row['explanation']
#         img_uddipok = row.get('img_uddipok')
#         img_question = row.get('img_question')
#         img_explanation = row.get('img_explanation')
#         year_institute_data = row['year_institute']  # Example: "DiB '23, SB '19"
        
#         try:
#             subject = Subject.objects.get(subject_code=subject_code)
#             chapter = Chapter.objects.get(subject=subject, chapter_no=chapter_no)
#             topic = Topic.objects.get(chapter=chapter, topic_no=topic_no)
            
#             # Update or create the MCQ entry
#             mcq, created = Mcq_ict.objects.update_or_create(
#                 subject=subject,
#                 chapter=chapter,
#                 topic=topic,
#                 question=question,
#                 defaults={
#                     'option1': option1,
#                     'option2': option2,
#                     'option3': option3,
#                     'option4': option4,
#                     'answer': answer,
#                     'uddipok': uddipok,
#                     'explanation': explanation,
#                     'img_uddipok': img_uddipok,
#                     'img_question': img_question,
#                     'img_explanation': img_explanation
#                 }
#             )

#             # Clear current institutes and years
#             mcq.institutes.clear()
#             mcq.years.clear()

#             # Parsing and assigning institutes and years
#             year_institute_pairs = year_institute_data.split(', ')
#             for pair in year_institute_pairs:
#                 parts = pair.split(" '")
                
#                 if len(parts) == 2:  # Expected format
#                     institute_code = parts[0].strip()
#                     year = parts[1].strip()
                    
#                     try:
#                         institute = Institute.objects.get(institute_code=institute_code)
#                         year_code = Year.objects.get(year_code=year)

#                         # Add to ManyToMany relationships
#                         mcq.institutes.add(institute)
#                         mcq.years.add(year_code)
                    
#                     except Institute.DoesNotExist:
#                         print(f"Institute with code {institute_code} does not exist")
#                     except Year.DoesNotExist:
#                         print(f"Year with code {year} does not exist")

#             mcq.save()  # Ensure MCQ is saved after updates

#             if created:
#                 print(f"Inserted new MCQ for {subject_code} - Chapter {chapter_no}")
#             else:
#                 print(f"Updated existing MCQ for {subject_code} - Chapter {chapter_no}")
        
#         except Subject.DoesNotExist:
#             print(f"Subject with code {subject_code} does not exist")
#         except Chapter.DoesNotExist:
#             print(f"Chapter {chapter_no} for subject {subject_code} does not exist")
#         except Topic.DoesNotExist:
#             print(f"Topic {topic_no} for chapter {chapter_no} does not exist")
