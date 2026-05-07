import os
import sys
import django

sys.path.append('E:/Running/cheradip/bcheradip')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

import csv
from cheradip.models import InstituteType, Institute  # Ensure correct model names

csv_file_path = 'C:\\Users\\sasha\\Desktop\\cheradip_database - Institute.csv'

with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)

    for row in reader:
        institute_code = row['institute_code']
        institute_name = row['institute_name']
        institute_type_name = row['institute_type']  # Read institute type name from CSV

        try:
            # Lookup InstituteType using the correct field 'type_name'
            institute_type_instance = InstituteType.objects.get(type_name=institute_type_name)
            
            # Create or update the Institute instance
            institute, created = Institute.objects.update_or_create(
                institute_code=institute_code,
                defaults={
                    'institute_name': institute_name,
                    'institute_type': institute_type_instance
                }
            )

            if created:
                print(f"Inserted Institute: {institute_name} with code {institute_code}")
            else:
                print(f"Updated Institute: {institute_name} with code {institute_code}")

        except InstituteType.DoesNotExist:
            print(f"Institution type with name '{institute_type_name}' does not exist")
        except Exception as e:
            print(f"An error occurred: {e}")
