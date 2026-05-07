import os
import sys
import django
import logging
import csv

# Disable logging if necessary
logging.disable(logging.CRITICAL)

# Set up Django environment
sys.path.append('E:/Running/cheradip/bcheradip')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

# Import relevant models
from cheradip.models import Subject, Chapter, Topic, Mcq_ict, Institute, Year, InstituteType, InstituteUnit

# Path to the CSV file
csv_file_path = 'C:\\Users\\sasha\\Desktop\\cheradip_database - InstituteBranch.csv'

# Open and read the CSV file
with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)

    # Loop through each row in the CSV
    for row in reader:
        unit_name = row['unit']
        institute_codes = row['institute'].split(',')  # Comma-separated institute codes
        
        for institute_code in institute_codes:
            institute_code = institute_code.strip()  # Clean up any leading/trailing whitespace
            
            try:
                # Fetch the Institute using the institute_code
                institute = Institute.objects.get(institute_code=institute_code)
                print(f"Found Institute: {institute.institute_name} with code {institute_code}")

                institute_id = institute.id

                institute_type = institute.institute_type
                print(f"InstituteType for {institute.institute_name}: {institute_type.type_name}")
                
                # Fetch or create the InstituteUnit, linking it to the found Institute
                unit, created_unit = InstituteUnit.objects.update_or_create(
                    unit=unit_name,
                    institute_id=institute_id # Any default values you want to update can be passed here
                )
                
                if created_unit:
                    print(f"Created new Unit: {unit_name}")
                else:
                    print(f"Updated existing Unit: {unit_name}")
            
            except Institute.DoesNotExist:
                print(f"Institute with code {institute_code} does not exist, skipping.")
                continue  # Skip to the next institute_code if not found
            
            except Exception as e:
                print(f"Error creating or updating Unit {unit_name} for Institute {institute_code}: {e}")

print("Import completed.")
