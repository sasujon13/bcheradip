import os
import sys
import django
import logging

logging.disable(logging.CRITICAL)

sys.path.append('E:/Running/cheradip/bcheradip')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

import csv
from cheradip.models import Subject, Chapter, Topic, Mcq_ict, Institute, Year, InstituteType, InstituteUnit

csv_file_path = 'C:\\Users\\sasha\\Desktop\\mcq_ict.csv'

answer_mapping = {
    '1': '1',
    '2': '2',
    '3': '3',
    '4': '4'
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
        year_institute_data = row['year_institute']

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
                    'answer': mapped_answer,
                    'uddipok': uddipok,
                    'explanation': explanation,
                    'img_uddipok': img_uddipok,
                    'img_question': img_question,
                    'img_explanation': img_explanation
                }
            )

            current_institutes = set(mcq.institutes.all())
            current_instituteTypes = set(mcq.instituteTypes.all())
            current_years = set(mcq.years.all())
            current_units = set(mcq.instituteUnits.all())
            
            year_institute_pairs = year_institute_data.split(', ')
            
            new_institutes = set()
            new_instituteTypes = set()
            new_years = set()
            new_units = set()

            for pair in year_institute_pairs:
                pair = pair.strip()
                if " '" in pair:
                    parts = pair.split(" '")
                    institute_code = parts[0].strip()
                    year = parts[1].strip()
                    if "-" in institute_code:
                        parts2 = institute_code.split("-")
                        institute_part = parts2[0].strip()
                        institute_unit = parts2[1].strip()

                        try:
                            institute = Institute.objects.get(institute_code=institute_part)
                            new_institutes.add(institute)

                            institute_type = institute.institute_type

                            year_code = Year.objects.get(year_code=year)
                            new_years.add(year_code)

                            unit = InstituteUnit.objects.get(unit=institute_unit, institute=institute)
                            if unit:
                                new_units.add(unit)

                            if institute_type:
                                new_instituteTypes.add(institute_type)

                        except Institute.DoesNotExist:
                            print(f"Institute with code '{institute_code}' does not exist.")
                        except Year.DoesNotExist:
                            print(f"Year with code '{year}' does not exist.")
                        except InstituteUnit.DoesNotExist:
                            print(f"Institute with unit '{institute_unit}' does not exist.")
                    else:
                        try:
                            institute = Institute.objects.get(institute_code=institute_code)
                            new_institutes.add(institute)

                            institute_type = institute.institute_type

                            year_code = Year.objects.get(year_code=year)
                            new_years.add(year_code)

                            if institute_type:
                                new_instituteTypes.add(institute_type)

                        except Institute.DoesNotExist:
                            print(f"Institute with code '{institute_code}' does not exist.")
                        except Year.DoesNotExist:
                            print(f"Year with code '{year}' does not exist.")
                else:
                    institute_code = pair.strip()
                    if "-" in institute_code:
                        parts2 = institute_code.split("-")
                        institute_part = parts2[0].strip()
                        institute_unit = parts2[1].strip()

                        try:
                            institute = Institute.objects.get(institute_code=institute_part)
                            new_institutes.add(institute)

                            institute_type = institute.institute_type

                            year_code = Year.objects.get(year_code=year)
                            new_years.add(year_code)

                            unit = InstituteUnit.objects.get(unit=institute_unit, institute=institute)
                            if unit.exists():
                                new_units.add(unit)

                            if institute_type:
                                new_instituteTypes.add(institute_type)

                        except Institute.DoesNotExist:
                            print(f"Institute with code '{institute_code}' does not exist.")
                        except Year.DoesNotExist:
                            print(f"Year with code '{year}' does not exist.")
                        except InstituteUnit.DoesNotExist:
                            print(f"Institute with unit '{institute_unit}' does not exist.")
                    else:
                        try:
                            institute = Institute.objects.get(institute_code=institute_code)
                            new_institutes.add(institute)

                            institute_type = institute.institute_type

                            year_code = Year.objects.get(year_code=year)
                            new_years.add(year_code)

                            if institute_type:
                                new_instituteTypes.add(institute_type)

                        except Institute.DoesNotExist:
                            print(f"Institute with code '{institute_code}' does not exist.")
                        except Year.DoesNotExist:
                            print(f"Year with code '{year}' does not exist.")
                
                institutes_to_add = new_institutes - current_institutes
                institutes_to_remove = current_institutes - new_institutes

                for institute in institutes_to_add:
                    mcq.institutes.add(institute)

                for institute in institutes_to_remove:
                    mcq.institutes.remove(institute)

                # Update institutes: Add new ones, remove outdated ones
                instituteTypes_to_add = new_instituteTypes - current_instituteTypes
                instituteTypes_to_remove = current_instituteTypes - new_instituteTypes

                for instituteType in instituteTypes_to_add:
                    mcq.instituteTypes.add(instituteType)

                for instituteType in instituteTypes_to_remove:
                    mcq.instituteTypes.remove(instituteType)

                # Update years: Add new ones, remove outdated ones
                years_to_add = new_years - current_years
                years_to_remove = current_years - new_years

                for year_code in years_to_add:
                    mcq.years.add(year_code)

                for year_code in years_to_remove:
                    mcq.years.remove(year_code)
                # Update years: Add new ones, remove outdated ones
                
                units_to_add = new_units - current_units
                units_to_remove = current_units - new_units

                for unit in units_to_add:
                    mcq.instituteUnits.add(unit)

                for unit in units_to_remove:
                    mcq.instituteUnits.remove(unit)

        except Exception as e:
            print(f"An error occurred while processing the row: {e}")

print("Processing complete.")
