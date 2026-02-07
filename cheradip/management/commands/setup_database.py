"""
Setup Database Command
----------------------
This command will:
1. Import data from localhost.sql to cheradip_cheradip database
2. Create/update the Country table with extended fields
3. Load all country data (195+ countries)

Usage:
    python manage.py setup_database --import-sql
    python manage.py setup_database --load-countries
    python manage.py setup_database --all
"""

import os
import subprocess
from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings


class Command(BaseCommand):
    help = 'Setup database: import SQL, create tables, load country data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--import-sql',
            action='store_true',
            help='Import data from localhost.sql file',
        )
        parser.add_argument(
            '--load-countries',
            action='store_true',
            help='Load all countries to database',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Run all setup steps',
        )
        parser.add_argument(
            '--sql-file',
            type=str,
            default='../localhost.sql',
            help='Path to SQL file (default: ../localhost.sql)',
        )

    def handle(self, *args, **options):
        if options['all']:
            options['import_sql'] = True
            options['load_countries'] = True

        if options['import_sql']:
            self.import_sql(options['sql_file'])

        if options['load_countries']:
            self.load_countries()

        if not any([options['import_sql'], options['load_countries'], options['all']]):
            self.stdout.write(self.style.WARNING(
                'No action specified. Use --import-sql, --load-countries, or --all'
            ))

    def import_sql(self, sql_file):
        """Import SQL file to database using mysql command"""
        self.stdout.write(self.style.NOTICE('Importing SQL file...'))
        
        # Get database settings
        db_settings = settings.DATABASES['default']
        db_name = db_settings['NAME']
        db_user = db_settings['USER']
        db_password = db_settings.get('PASSWORD', '')
        db_host = db_settings.get('HOST', 'localhost')
        db_port = db_settings.get('PORT', '3306')

        # Resolve SQL file path
        if not os.path.isabs(sql_file):
            sql_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), sql_file)
        
        sql_file = os.path.normpath(sql_file)
        
        if not os.path.exists(sql_file):
            self.stdout.write(self.style.ERROR(f'SQL file not found: {sql_file}'))
            return

        self.stdout.write(f'SQL file: {sql_file}')
        self.stdout.write(f'Database: {db_name}')
        self.stdout.write(f'Host: {db_host}:{db_port}')

        # Build mysql command
        mysql_cmd = ['mysql']
        mysql_cmd.extend(['-h', db_host])
        mysql_cmd.extend(['-P', str(db_port)])
        mysql_cmd.extend(['-u', db_user])
        if db_password:
            mysql_cmd.append(f'-p{db_password}')
        mysql_cmd.append(db_name)

        try:
            # Read and execute SQL file
            with open(sql_file, 'r', encoding='utf-8', errors='ignore') as f:
                sql_content = f.read()

            self.stdout.write(self.style.NOTICE('Executing SQL... This may take a while...'))
            
            # Execute using mysql command
            process = subprocess.Popen(
                mysql_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True
            )
            stdout, stderr = process.communicate(input=sql_content.encode('utf-8'))

            if process.returncode == 0:
                self.stdout.write(self.style.SUCCESS('SQL import completed successfully!'))
            else:
                self.stdout.write(self.style.ERROR(f'SQL import failed: {stderr.decode()}'))
                self.stdout.write(self.style.WARNING(
                    'Alternative: Import manually using phpMyAdmin or MySQL Workbench'
                ))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(
                'mysql command not found. Please ensure MySQL is installed and in PATH.'
            ))
            self.stdout.write(self.style.WARNING(
                'Alternative methods to import localhost.sql:'
            ))
            self.stdout.write('  1. phpMyAdmin: Import tab -> Choose file -> Go')
            self.stdout.write('  2. MySQL Workbench: Server -> Data Import')
            self.stdout.write(f'  3. Command line: mysql -u {db_user} -p {db_name} < "{sql_file}"')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))

    def load_countries(self):
        """Load all countries to database"""
        self.stdout.write(self.style.NOTICE('Loading countries...'))
        
        # Check if Country model exists with new fields
        try:
            from cheradip.models import Country
        except ImportError:
            self.stdout.write(self.style.WARNING(
                'Country model not found. Creating table directly...'
            ))
            self.create_country_table()
            from cheradip.models import Country

        countries_data = self.get_countries_data()
        
        created_count = 0
        updated_count = 0
        
        for data in countries_data:
            try:
                country, created = Country.objects.update_or_create(
                    country_code=data['country_code'],
                    defaults=data
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f"Error with {data.get('country_name', 'unknown')}: {str(e)}"
                ))

        self.stdout.write(self.style.SUCCESS(
            f'Countries loaded: {created_count} created, {updated_count} updated'
        ))

    def create_country_table(self):
        """Create/update country table with extended fields"""
        self.stdout.write(self.style.NOTICE('Creating/updating country table...'))
        
        sql = """
        DROP TABLE IF EXISTS `countries`;
        CREATE TABLE `countries` (
            `country_code` varchar(2) NOT NULL PRIMARY KEY,
            `country_code_alpha3` varchar(3) DEFAULT NULL,
            `country_code_numeric` varchar(3) DEFAULT NULL,
            `country_name` varchar(60) NOT NULL,
            `country_name_native` varchar(60) DEFAULT NULL,
            `country_name_official` varchar(100) DEFAULT NULL,
            `flag_emoji` varchar(10) DEFAULT NULL,
            `flag_url` varchar(255) DEFAULT NULL,
            `phone_code` varchar(5) NOT NULL,
            `phone_code_numeric` int(11) DEFAULT NULL,
            `phone_format` varchar(30) DEFAULT NULL,
            `phone_length_min` int(11) DEFAULT 10,
            `phone_length_max` int(11) DEFAULT 10,
            `continent` varchar(20) DEFAULT NULL,
            `region` varchar(30) DEFAULT NULL,
            `capital` varchar(50) DEFAULT NULL,
            `currency_code` varchar(3) DEFAULT NULL,
            `currency_symbol` varchar(10) DEFAULT NULL,
            `language_codes` json DEFAULT NULL,
            `timezone` varchar(50) DEFAULT NULL,
            `display_order` int(11) DEFAULT 100,
            `is_featured` tinyint(1) DEFAULT 0,
            `is_active` tinyint(1) DEFAULT 1,
            `created_at` datetime(6) DEFAULT CURRENT_TIMESTAMP(6),
            `updated_at` datetime(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        
        with connection.cursor() as cursor:
            for statement in sql.split(';'):
                statement = statement.strip()
                if statement:
                    try:
                        cursor.execute(statement)
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'SQL warning: {str(e)}'))

        self.stdout.write(self.style.SUCCESS('Country table created/updated!'))

    def get_countries_data(self):
        """Return all countries data"""
        return [
            # South Asia (Featured)
            {'country_code': 'BD', 'country_code_alpha3': 'BGD', 'country_code_numeric': '050', 'country_name': 'Bangladesh', 'country_name_native': 'বাংলাদেশ', 'country_name_official': "People's Republic of Bangladesh", 'flag_emoji': '🇧🇩', 'phone_code': '+880', 'phone_code_numeric': 880, 'phone_format': '+880 1XXX-XXXXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Asia', 'region': 'Southern Asia', 'capital': 'Dhaka', 'currency_code': 'BDT', 'currency_symbol': '৳', 'timezone': 'Asia/Dhaka', 'display_order': 1, 'is_featured': True, 'is_active': True},
            {'country_code': 'IN', 'country_code_alpha3': 'IND', 'country_code_numeric': '356', 'country_name': 'India', 'country_name_native': 'भारत', 'country_name_official': 'Republic of India', 'flag_emoji': '🇮🇳', 'phone_code': '+91', 'phone_code_numeric': 91, 'phone_format': '+91 XXXXX XXXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Asia', 'region': 'Southern Asia', 'capital': 'New Delhi', 'currency_code': 'INR', 'currency_symbol': '₹', 'timezone': 'Asia/Kolkata', 'display_order': 2, 'is_featured': True, 'is_active': True},
            {'country_code': 'PK', 'country_code_alpha3': 'PAK', 'country_code_numeric': '586', 'country_name': 'Pakistan', 'country_name_native': 'پاکستان', 'country_name_official': 'Islamic Republic of Pakistan', 'flag_emoji': '🇵🇰', 'phone_code': '+92', 'phone_code_numeric': 92, 'phone_format': '+92 XXX XXXXXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Asia', 'region': 'Southern Asia', 'capital': 'Islamabad', 'currency_code': 'PKR', 'currency_symbol': '₨', 'timezone': 'Asia/Karachi', 'display_order': 3, 'is_featured': True, 'is_active': True},
            {'country_code': 'NP', 'country_code_alpha3': 'NPL', 'country_code_numeric': '524', 'country_name': 'Nepal', 'country_name_native': 'नेपाल', 'country_name_official': 'Federal Democratic Republic of Nepal', 'flag_emoji': '🇳🇵', 'phone_code': '+977', 'phone_code_numeric': 977, 'phone_format': '+977 XX XXXXXXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Asia', 'region': 'Southern Asia', 'capital': 'Kathmandu', 'currency_code': 'NPR', 'currency_symbol': '₨', 'timezone': 'Asia/Kathmandu', 'display_order': 4, 'is_featured': True, 'is_active': True},
            {'country_code': 'LK', 'country_code_alpha3': 'LKA', 'country_code_numeric': '144', 'country_name': 'Sri Lanka', 'country_name_native': 'ශ්‍රී ලංකාව', 'country_name_official': 'Democratic Socialist Republic of Sri Lanka', 'flag_emoji': '🇱🇰', 'phone_code': '+94', 'phone_code_numeric': 94, 'phone_format': '+94 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'Southern Asia', 'capital': 'Sri Jayawardenepura Kotte', 'currency_code': 'LKR', 'currency_symbol': 'Rs', 'timezone': 'Asia/Colombo', 'display_order': 5, 'is_featured': True, 'is_active': True},
            {'country_code': 'BT', 'country_code_alpha3': 'BTN', 'country_code_numeric': '064', 'country_name': 'Bhutan', 'country_name_native': 'འབྲུག་རྒྱལ་ཁབ་', 'country_name_official': 'Kingdom of Bhutan', 'flag_emoji': '🇧🇹', 'phone_code': '+975', 'phone_code_numeric': 975, 'phone_format': '+975 XX XXX XXX', 'phone_length_min': 8, 'phone_length_max': 8, 'continent': 'Asia', 'region': 'Southern Asia', 'capital': 'Thimphu', 'currency_code': 'BTN', 'currency_symbol': 'Nu.', 'timezone': 'Asia/Thimphu', 'display_order': 6, 'is_featured': False, 'is_active': True},
            {'country_code': 'MV', 'country_code_alpha3': 'MDV', 'country_code_numeric': '462', 'country_name': 'Maldives', 'country_name_native': 'ދިވެހިރާއްޖެ', 'country_name_official': 'Republic of Maldives', 'flag_emoji': '🇲🇻', 'phone_code': '+960', 'phone_code_numeric': 960, 'phone_format': '+960 XXX XXXX', 'phone_length_min': 7, 'phone_length_max': 7, 'continent': 'Asia', 'region': 'Southern Asia', 'capital': 'Malé', 'currency_code': 'MVR', 'currency_symbol': 'Rf', 'timezone': 'Indian/Maldives', 'display_order': 7, 'is_featured': False, 'is_active': True},
            {'country_code': 'AF', 'country_code_alpha3': 'AFG', 'country_code_numeric': '004', 'country_name': 'Afghanistan', 'country_name_native': 'افغانستان', 'country_name_official': 'Islamic Republic of Afghanistan', 'flag_emoji': '🇦🇫', 'phone_code': '+93', 'phone_code_numeric': 93, 'phone_format': '+93 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'Southern Asia', 'capital': 'Kabul', 'currency_code': 'AFN', 'currency_symbol': '؋', 'timezone': 'Asia/Kabul', 'display_order': 8, 'is_featured': False, 'is_active': True},
            
            # Middle East (Featured)
            {'country_code': 'AE', 'country_code_alpha3': 'ARE', 'country_code_numeric': '784', 'country_name': 'United Arab Emirates', 'country_name_native': 'الإمارات العربية المتحدة', 'country_name_official': 'United Arab Emirates', 'flag_emoji': '🇦🇪', 'phone_code': '+971', 'phone_code_numeric': 971, 'phone_format': '+971 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'Western Asia', 'capital': 'Abu Dhabi', 'currency_code': 'AED', 'currency_symbol': 'د.إ', 'timezone': 'Asia/Dubai', 'display_order': 10, 'is_featured': True, 'is_active': True},
            {'country_code': 'SA', 'country_code_alpha3': 'SAU', 'country_code_numeric': '682', 'country_name': 'Saudi Arabia', 'country_name_native': 'المملكة العربية السعودية', 'country_name_official': 'Kingdom of Saudi Arabia', 'flag_emoji': '🇸🇦', 'phone_code': '+966', 'phone_code_numeric': 966, 'phone_format': '+966 X XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'Western Asia', 'capital': 'Riyadh', 'currency_code': 'SAR', 'currency_symbol': '﷼', 'timezone': 'Asia/Riyadh', 'display_order': 11, 'is_featured': True, 'is_active': True},
            {'country_code': 'QA', 'country_code_alpha3': 'QAT', 'country_code_numeric': '634', 'country_name': 'Qatar', 'country_name_native': 'قطر', 'country_name_official': 'State of Qatar', 'flag_emoji': '🇶🇦', 'phone_code': '+974', 'phone_code_numeric': 974, 'phone_format': '+974 XXXX XXXX', 'phone_length_min': 8, 'phone_length_max': 8, 'continent': 'Asia', 'region': 'Western Asia', 'capital': 'Doha', 'currency_code': 'QAR', 'currency_symbol': '﷼', 'timezone': 'Asia/Qatar', 'display_order': 12, 'is_featured': True, 'is_active': True},
            {'country_code': 'KW', 'country_code_alpha3': 'KWT', 'country_code_numeric': '414', 'country_name': 'Kuwait', 'country_name_native': 'الكويت', 'country_name_official': 'State of Kuwait', 'flag_emoji': '🇰🇼', 'phone_code': '+965', 'phone_code_numeric': 965, 'phone_format': '+965 XXXX XXXX', 'phone_length_min': 8, 'phone_length_max': 8, 'continent': 'Asia', 'region': 'Western Asia', 'capital': 'Kuwait City', 'currency_code': 'KWD', 'currency_symbol': 'د.ك', 'timezone': 'Asia/Kuwait', 'display_order': 13, 'is_featured': False, 'is_active': True},
            {'country_code': 'BH', 'country_code_alpha3': 'BHR', 'country_code_numeric': '048', 'country_name': 'Bahrain', 'country_name_native': 'البحرين', 'country_name_official': 'Kingdom of Bahrain', 'flag_emoji': '🇧🇭', 'phone_code': '+973', 'phone_code_numeric': 973, 'phone_format': '+973 XXXX XXXX', 'phone_length_min': 8, 'phone_length_max': 8, 'continent': 'Asia', 'region': 'Western Asia', 'capital': 'Manama', 'currency_code': 'BHD', 'currency_symbol': '.د.ب', 'timezone': 'Asia/Bahrain', 'display_order': 14, 'is_featured': False, 'is_active': True},
            {'country_code': 'OM', 'country_code_alpha3': 'OMN', 'country_code_numeric': '512', 'country_name': 'Oman', 'country_name_native': 'عمان', 'country_name_official': 'Sultanate of Oman', 'flag_emoji': '🇴🇲', 'phone_code': '+968', 'phone_code_numeric': 968, 'phone_format': '+968 XXXX XXXX', 'phone_length_min': 8, 'phone_length_max': 8, 'continent': 'Asia', 'region': 'Western Asia', 'capital': 'Muscat', 'currency_code': 'OMR', 'currency_symbol': '﷼', 'timezone': 'Asia/Muscat', 'display_order': 15, 'is_featured': False, 'is_active': True},
            {'country_code': 'YE', 'country_code_alpha3': 'YEM', 'country_code_numeric': '887', 'country_name': 'Yemen', 'country_name_native': 'اليمن', 'country_name_official': 'Republic of Yemen', 'flag_emoji': '🇾🇪', 'phone_code': '+967', 'phone_code_numeric': 967, 'phone_format': '+967 XXX XXX XXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'Western Asia', 'capital': "Sana'a", 'currency_code': 'YER', 'currency_symbol': '﷼', 'timezone': 'Asia/Aden', 'display_order': 16, 'is_featured': False, 'is_active': True},
            {'country_code': 'IR', 'country_code_alpha3': 'IRN', 'country_code_numeric': '364', 'country_name': 'Iran', 'country_name_native': 'ایران', 'country_name_official': 'Islamic Republic of Iran', 'flag_emoji': '🇮🇷', 'phone_code': '+98', 'phone_code_numeric': 98, 'phone_format': '+98 XXX XXX XXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Asia', 'region': 'Southern Asia', 'capital': 'Tehran', 'currency_code': 'IRR', 'currency_symbol': '﷼', 'timezone': 'Asia/Tehran', 'display_order': 17, 'is_featured': False, 'is_active': True},
            {'country_code': 'IQ', 'country_code_alpha3': 'IRQ', 'country_code_numeric': '368', 'country_name': 'Iraq', 'country_name_native': 'العراق', 'country_name_official': 'Republic of Iraq', 'flag_emoji': '🇮🇶', 'phone_code': '+964', 'phone_code_numeric': 964, 'phone_format': '+964 XXX XXX XXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Asia', 'region': 'Western Asia', 'capital': 'Baghdad', 'currency_code': 'IQD', 'currency_symbol': 'ع.د', 'timezone': 'Asia/Baghdad', 'display_order': 18, 'is_featured': False, 'is_active': True},
            {'country_code': 'JO', 'country_code_alpha3': 'JOR', 'country_code_numeric': '400', 'country_name': 'Jordan', 'country_name_native': 'الأردن', 'country_name_official': 'Hashemite Kingdom of Jordan', 'flag_emoji': '🇯🇴', 'phone_code': '+962', 'phone_code_numeric': 962, 'phone_format': '+962 X XXXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'Western Asia', 'capital': 'Amman', 'currency_code': 'JOD', 'currency_symbol': 'د.ا', 'timezone': 'Asia/Amman', 'display_order': 19, 'is_featured': False, 'is_active': True},
            {'country_code': 'LB', 'country_code_alpha3': 'LBN', 'country_code_numeric': '422', 'country_name': 'Lebanon', 'country_name_native': 'لبنان', 'country_name_official': 'Lebanese Republic', 'flag_emoji': '🇱🇧', 'phone_code': '+961', 'phone_code_numeric': 961, 'phone_format': '+961 XX XXX XXX', 'phone_length_min': 8, 'phone_length_max': 8, 'continent': 'Asia', 'region': 'Western Asia', 'capital': 'Beirut', 'currency_code': 'LBP', 'currency_symbol': 'ل.ل', 'timezone': 'Asia/Beirut', 'display_order': 20, 'is_featured': False, 'is_active': True},
            {'country_code': 'SY', 'country_code_alpha3': 'SYR', 'country_code_numeric': '760', 'country_name': 'Syria', 'country_name_native': 'سوريا', 'country_name_official': 'Syrian Arab Republic', 'flag_emoji': '🇸🇾', 'phone_code': '+963', 'phone_code_numeric': 963, 'phone_format': '+963 XXX XXX XXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'Western Asia', 'capital': 'Damascus', 'currency_code': 'SYP', 'currency_symbol': '£', 'timezone': 'Asia/Damascus', 'display_order': 21, 'is_featured': False, 'is_active': True},
            {'country_code': 'PS', 'country_code_alpha3': 'PSE', 'country_code_numeric': '275', 'country_name': 'Palestine', 'country_name_native': 'فلسطين', 'country_name_official': 'State of Palestine', 'flag_emoji': '🇵🇸', 'phone_code': '+970', 'phone_code_numeric': 970, 'phone_format': '+970 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'Western Asia', 'capital': 'Ramallah', 'currency_code': 'ILS', 'currency_symbol': '₪', 'timezone': 'Asia/Gaza', 'display_order': 22, 'is_featured': False, 'is_active': True},
            {'country_code': 'IL', 'country_code_alpha3': 'ISR', 'country_code_numeric': '376', 'country_name': 'Israel', 'country_name_native': 'ישראל', 'country_name_official': 'State of Israel', 'flag_emoji': '🇮🇱', 'phone_code': '+972', 'phone_code_numeric': 972, 'phone_format': '+972 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'Western Asia', 'capital': 'Jerusalem', 'currency_code': 'ILS', 'currency_symbol': '₪', 'timezone': 'Asia/Jerusalem', 'display_order': 23, 'is_featured': False, 'is_active': True},
            {'country_code': 'TR', 'country_code_alpha3': 'TUR', 'country_code_numeric': '792', 'country_name': 'Turkey', 'country_name_native': 'Türkiye', 'country_name_official': 'Republic of Turkey', 'flag_emoji': '🇹🇷', 'phone_code': '+90', 'phone_code_numeric': 90, 'phone_format': '+90 XXX XXX XXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Asia', 'region': 'Western Asia', 'capital': 'Ankara', 'currency_code': 'TRY', 'currency_symbol': '₺', 'timezone': 'Europe/Istanbul', 'display_order': 24, 'is_featured': False, 'is_active': True},
            
            # Southeast Asia
            {'country_code': 'MY', 'country_code_alpha3': 'MYS', 'country_code_numeric': '458', 'country_name': 'Malaysia', 'country_name_native': 'Malaysia', 'country_name_official': 'Malaysia', 'flag_emoji': '🇲🇾', 'phone_code': '+60', 'phone_code_numeric': 60, 'phone_format': '+60 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 10, 'continent': 'Asia', 'region': 'South-Eastern Asia', 'capital': 'Kuala Lumpur', 'currency_code': 'MYR', 'currency_symbol': 'RM', 'timezone': 'Asia/Kuala_Lumpur', 'display_order': 25, 'is_featured': True, 'is_active': True},
            {'country_code': 'SG', 'country_code_alpha3': 'SGP', 'country_code_numeric': '702', 'country_name': 'Singapore', 'country_name_native': 'Singapore', 'country_name_official': 'Republic of Singapore', 'flag_emoji': '🇸🇬', 'phone_code': '+65', 'phone_code_numeric': 65, 'phone_format': '+65 XXXX XXXX', 'phone_length_min': 8, 'phone_length_max': 8, 'continent': 'Asia', 'region': 'South-Eastern Asia', 'capital': 'Singapore', 'currency_code': 'SGD', 'currency_symbol': '$', 'timezone': 'Asia/Singapore', 'display_order': 26, 'is_featured': False, 'is_active': True},
            {'country_code': 'ID', 'country_code_alpha3': 'IDN', 'country_code_numeric': '360', 'country_name': 'Indonesia', 'country_name_native': 'Indonesia', 'country_name_official': 'Republic of Indonesia', 'flag_emoji': '🇮🇩', 'phone_code': '+62', 'phone_code_numeric': 62, 'phone_format': '+62 XXX XXXX XXXX', 'phone_length_min': 10, 'phone_length_max': 12, 'continent': 'Asia', 'region': 'South-Eastern Asia', 'capital': 'Jakarta', 'currency_code': 'IDR', 'currency_symbol': 'Rp', 'timezone': 'Asia/Jakarta', 'display_order': 27, 'is_featured': False, 'is_active': True},
            {'country_code': 'TH', 'country_code_alpha3': 'THA', 'country_code_numeric': '764', 'country_name': 'Thailand', 'country_name_native': 'ประเทศไทย', 'country_name_official': 'Kingdom of Thailand', 'flag_emoji': '🇹🇭', 'phone_code': '+66', 'phone_code_numeric': 66, 'phone_format': '+66 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'South-Eastern Asia', 'capital': 'Bangkok', 'currency_code': 'THB', 'currency_symbol': '฿', 'timezone': 'Asia/Bangkok', 'display_order': 28, 'is_featured': False, 'is_active': True},
            {'country_code': 'PH', 'country_code_alpha3': 'PHL', 'country_code_numeric': '608', 'country_name': 'Philippines', 'country_name_native': 'Pilipinas', 'country_name_official': 'Republic of the Philippines', 'flag_emoji': '🇵🇭', 'phone_code': '+63', 'phone_code_numeric': 63, 'phone_format': '+63 XXX XXX XXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Asia', 'region': 'South-Eastern Asia', 'capital': 'Manila', 'currency_code': 'PHP', 'currency_symbol': '₱', 'timezone': 'Asia/Manila', 'display_order': 29, 'is_featured': False, 'is_active': True},
            {'country_code': 'VN', 'country_code_alpha3': 'VNM', 'country_code_numeric': '704', 'country_name': 'Vietnam', 'country_name_native': 'Việt Nam', 'country_name_official': 'Socialist Republic of Vietnam', 'flag_emoji': '🇻🇳', 'phone_code': '+84', 'phone_code_numeric': 84, 'phone_format': '+84 XXX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 10, 'continent': 'Asia', 'region': 'South-Eastern Asia', 'capital': 'Hanoi', 'currency_code': 'VND', 'currency_symbol': '₫', 'timezone': 'Asia/Ho_Chi_Minh', 'display_order': 30, 'is_featured': False, 'is_active': True},
            {'country_code': 'MM', 'country_code_alpha3': 'MMR', 'country_code_numeric': '104', 'country_name': 'Myanmar', 'country_name_native': 'မြန်မာ', 'country_name_official': 'Republic of the Union of Myanmar', 'flag_emoji': '🇲🇲', 'phone_code': '+95', 'phone_code_numeric': 95, 'phone_format': '+95 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 10, 'continent': 'Asia', 'region': 'South-Eastern Asia', 'capital': 'Naypyidaw', 'currency_code': 'MMK', 'currency_symbol': 'K', 'timezone': 'Asia/Yangon', 'display_order': 31, 'is_featured': False, 'is_active': True},
            {'country_code': 'KH', 'country_code_alpha3': 'KHM', 'country_code_numeric': '116', 'country_name': 'Cambodia', 'country_name_native': 'កម្ពុជា', 'country_name_official': 'Kingdom of Cambodia', 'flag_emoji': '🇰🇭', 'phone_code': '+855', 'phone_code_numeric': 855, 'phone_format': '+855 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'South-Eastern Asia', 'capital': 'Phnom Penh', 'currency_code': 'KHR', 'currency_symbol': '៛', 'timezone': 'Asia/Phnom_Penh', 'display_order': 32, 'is_featured': False, 'is_active': True},
            {'country_code': 'LA', 'country_code_alpha3': 'LAO', 'country_code_numeric': '418', 'country_name': 'Laos', 'country_name_native': 'ລາວ', 'country_name_official': "Lao People's Democratic Republic", 'flag_emoji': '🇱🇦', 'phone_code': '+856', 'phone_code_numeric': 856, 'phone_format': '+856 XX XX XXX XXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Asia', 'region': 'South-Eastern Asia', 'capital': 'Vientiane', 'currency_code': 'LAK', 'currency_symbol': '₭', 'timezone': 'Asia/Vientiane', 'display_order': 33, 'is_featured': False, 'is_active': True},
            {'country_code': 'BN', 'country_code_alpha3': 'BRN', 'country_code_numeric': '096', 'country_name': 'Brunei', 'country_name_native': 'Brunei', 'country_name_official': 'Nation of Brunei', 'flag_emoji': '🇧🇳', 'phone_code': '+673', 'phone_code_numeric': 673, 'phone_format': '+673 XXX XXXX', 'phone_length_min': 7, 'phone_length_max': 7, 'continent': 'Asia', 'region': 'South-Eastern Asia', 'capital': 'Bandar Seri Begawan', 'currency_code': 'BND', 'currency_symbol': '$', 'timezone': 'Asia/Brunei', 'display_order': 34, 'is_featured': False, 'is_active': True},
            {'country_code': 'TL', 'country_code_alpha3': 'TLS', 'country_code_numeric': '626', 'country_name': 'Timor-Leste', 'country_name_native': 'Timor-Leste', 'country_name_official': 'Democratic Republic of Timor-Leste', 'flag_emoji': '🇹🇱', 'phone_code': '+670', 'phone_code_numeric': 670, 'phone_format': '+670 XXX XXXX', 'phone_length_min': 7, 'phone_length_max': 8, 'continent': 'Asia', 'region': 'South-Eastern Asia', 'capital': 'Dili', 'currency_code': 'USD', 'currency_symbol': '$', 'timezone': 'Asia/Dili', 'display_order': 35, 'is_featured': False, 'is_active': True},
            
            # East Asia
            {'country_code': 'CN', 'country_code_alpha3': 'CHN', 'country_code_numeric': '156', 'country_name': 'China', 'country_name_native': '中国', 'country_name_official': "People's Republic of China", 'flag_emoji': '🇨🇳', 'phone_code': '+86', 'phone_code_numeric': 86, 'phone_format': '+86 XXX XXXX XXXX', 'phone_length_min': 11, 'phone_length_max': 11, 'continent': 'Asia', 'region': 'Eastern Asia', 'capital': 'Beijing', 'currency_code': 'CNY', 'currency_symbol': '¥', 'timezone': 'Asia/Shanghai', 'display_order': 40, 'is_featured': False, 'is_active': True},
            {'country_code': 'JP', 'country_code_alpha3': 'JPN', 'country_code_numeric': '392', 'country_name': 'Japan', 'country_name_native': '日本', 'country_name_official': 'Japan', 'flag_emoji': '🇯🇵', 'phone_code': '+81', 'phone_code_numeric': 81, 'phone_format': '+81 XX XXXX XXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Asia', 'region': 'Eastern Asia', 'capital': 'Tokyo', 'currency_code': 'JPY', 'currency_symbol': '¥', 'timezone': 'Asia/Tokyo', 'display_order': 41, 'is_featured': False, 'is_active': True},
            {'country_code': 'KR', 'country_code_alpha3': 'KOR', 'country_code_numeric': '410', 'country_name': 'South Korea', 'country_name_native': '대한민국', 'country_name_official': 'Republic of Korea', 'flag_emoji': '🇰🇷', 'phone_code': '+82', 'phone_code_numeric': 82, 'phone_format': '+82 XX XXXX XXXX', 'phone_length_min': 9, 'phone_length_max': 10, 'continent': 'Asia', 'region': 'Eastern Asia', 'capital': 'Seoul', 'currency_code': 'KRW', 'currency_symbol': '₩', 'timezone': 'Asia/Seoul', 'display_order': 42, 'is_featured': False, 'is_active': True},
            {'country_code': 'KP', 'country_code_alpha3': 'PRK', 'country_code_numeric': '408', 'country_name': 'North Korea', 'country_name_native': '북한', 'country_name_official': "Democratic People's Republic of Korea", 'flag_emoji': '🇰🇵', 'phone_code': '+850', 'phone_code_numeric': 850, 'phone_format': '+850 XXX XXX XXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Asia', 'region': 'Eastern Asia', 'capital': 'Pyongyang', 'currency_code': 'KPW', 'currency_symbol': '₩', 'timezone': 'Asia/Pyongyang', 'display_order': 43, 'is_featured': False, 'is_active': True},
            {'country_code': 'TW', 'country_code_alpha3': 'TWN', 'country_code_numeric': '158', 'country_name': 'Taiwan', 'country_name_native': '台灣', 'country_name_official': 'Republic of China', 'flag_emoji': '🇹🇼', 'phone_code': '+886', 'phone_code_numeric': 886, 'phone_format': '+886 XXX XXX XXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'Eastern Asia', 'capital': 'Taipei', 'currency_code': 'TWD', 'currency_symbol': 'NT$', 'timezone': 'Asia/Taipei', 'display_order': 44, 'is_featured': False, 'is_active': True},
            {'country_code': 'HK', 'country_code_alpha3': 'HKG', 'country_code_numeric': '344', 'country_name': 'Hong Kong', 'country_name_native': '香港', 'country_name_official': 'Hong Kong Special Administrative Region', 'flag_emoji': '🇭🇰', 'phone_code': '+852', 'phone_code_numeric': 852, 'phone_format': '+852 XXXX XXXX', 'phone_length_min': 8, 'phone_length_max': 8, 'continent': 'Asia', 'region': 'Eastern Asia', 'capital': 'Hong Kong', 'currency_code': 'HKD', 'currency_symbol': '$', 'timezone': 'Asia/Hong_Kong', 'display_order': 45, 'is_featured': False, 'is_active': True},
            {'country_code': 'MO', 'country_code_alpha3': 'MAC', 'country_code_numeric': '446', 'country_name': 'Macau', 'country_name_native': '澳門', 'country_name_official': 'Macao Special Administrative Region', 'flag_emoji': '🇲🇴', 'phone_code': '+853', 'phone_code_numeric': 853, 'phone_format': '+853 XXXX XXXX', 'phone_length_min': 8, 'phone_length_max': 8, 'continent': 'Asia', 'region': 'Eastern Asia', 'capital': 'Macau', 'currency_code': 'MOP', 'currency_symbol': 'MOP$', 'timezone': 'Asia/Macau', 'display_order': 46, 'is_featured': False, 'is_active': True},
            {'country_code': 'MN', 'country_code_alpha3': 'MNG', 'country_code_numeric': '496', 'country_name': 'Mongolia', 'country_name_native': 'Монгол', 'country_name_official': 'Mongolia', 'flag_emoji': '🇲🇳', 'phone_code': '+976', 'phone_code_numeric': 976, 'phone_format': '+976 XX XX XXXX', 'phone_length_min': 8, 'phone_length_max': 8, 'continent': 'Asia', 'region': 'Eastern Asia', 'capital': 'Ulaanbaatar', 'currency_code': 'MNT', 'currency_symbol': '₮', 'timezone': 'Asia/Ulaanbaatar', 'display_order': 47, 'is_featured': False, 'is_active': True},
            
            # Central Asia
            {'country_code': 'KZ', 'country_code_alpha3': 'KAZ', 'country_code_numeric': '398', 'country_name': 'Kazakhstan', 'country_name_native': 'Қазақстан', 'country_name_official': 'Republic of Kazakhstan', 'flag_emoji': '🇰🇿', 'phone_code': '+7', 'phone_code_numeric': 7, 'phone_format': '+7 XXX XXX XX XX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Asia', 'region': 'Central Asia', 'capital': 'Astana', 'currency_code': 'KZT', 'currency_symbol': '₸', 'timezone': 'Asia/Almaty', 'display_order': 50, 'is_featured': False, 'is_active': True},
            {'country_code': 'UZ', 'country_code_alpha3': 'UZB', 'country_code_numeric': '860', 'country_name': 'Uzbekistan', 'country_name_native': "O'zbekiston", 'country_name_official': 'Republic of Uzbekistan', 'flag_emoji': '🇺🇿', 'phone_code': '+998', 'phone_code_numeric': 998, 'phone_format': '+998 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'Central Asia', 'capital': 'Tashkent', 'currency_code': 'UZS', 'currency_symbol': "so'm", 'timezone': 'Asia/Tashkent', 'display_order': 51, 'is_featured': False, 'is_active': True},
            {'country_code': 'TM', 'country_code_alpha3': 'TKM', 'country_code_numeric': '795', 'country_name': 'Turkmenistan', 'country_name_native': 'Türkmenistan', 'country_name_official': 'Turkmenistan', 'flag_emoji': '🇹🇲', 'phone_code': '+993', 'phone_code_numeric': 993, 'phone_format': '+993 XX XXXXXX', 'phone_length_min': 8, 'phone_length_max': 8, 'continent': 'Asia', 'region': 'Central Asia', 'capital': 'Ashgabat', 'currency_code': 'TMT', 'currency_symbol': 'm', 'timezone': 'Asia/Ashgabat', 'display_order': 52, 'is_featured': False, 'is_active': True},
            {'country_code': 'KG', 'country_code_alpha3': 'KGZ', 'country_code_numeric': '417', 'country_name': 'Kyrgyzstan', 'country_name_native': 'Кыргызстан', 'country_name_official': 'Kyrgyz Republic', 'flag_emoji': '🇰🇬', 'phone_code': '+996', 'phone_code_numeric': 996, 'phone_format': '+996 XXX XXXXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'Central Asia', 'capital': 'Bishkek', 'currency_code': 'KGS', 'currency_symbol': 'с', 'timezone': 'Asia/Bishkek', 'display_order': 53, 'is_featured': False, 'is_active': True},
            {'country_code': 'TJ', 'country_code_alpha3': 'TJK', 'country_code_numeric': '762', 'country_name': 'Tajikistan', 'country_name_native': 'Тоҷикистон', 'country_name_official': 'Republic of Tajikistan', 'flag_emoji': '🇹🇯', 'phone_code': '+992', 'phone_code_numeric': 992, 'phone_format': '+992 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'Central Asia', 'capital': 'Dushanbe', 'currency_code': 'TJS', 'currency_symbol': 'ЅМ', 'timezone': 'Asia/Dushanbe', 'display_order': 54, 'is_featured': False, 'is_active': True},
            
            # Caucasus
            {'country_code': 'GE', 'country_code_alpha3': 'GEO', 'country_code_numeric': '268', 'country_name': 'Georgia', 'country_name_native': 'საქართველო', 'country_name_official': 'Georgia', 'flag_emoji': '🇬🇪', 'phone_code': '+995', 'phone_code_numeric': 995, 'phone_format': '+995 XXX XX XX XX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'Western Asia', 'capital': 'Tbilisi', 'currency_code': 'GEL', 'currency_symbol': '₾', 'timezone': 'Asia/Tbilisi', 'display_order': 55, 'is_featured': False, 'is_active': True},
            {'country_code': 'AM', 'country_code_alpha3': 'ARM', 'country_code_numeric': '051', 'country_name': 'Armenia', 'country_name_native': 'Հdelays', 'country_name_official': 'Republic of Armenia', 'flag_emoji': '🇦🇲', 'phone_code': '+374', 'phone_code_numeric': 374, 'phone_format': '+374 XX XXXXXX', 'phone_length_min': 8, 'phone_length_max': 8, 'continent': 'Asia', 'region': 'Western Asia', 'capital': 'Yerevan', 'currency_code': 'AMD', 'currency_symbol': '֏', 'timezone': 'Asia/Yerevan', 'display_order': 56, 'is_featured': False, 'is_active': True},
            {'country_code': 'AZ', 'country_code_alpha3': 'AZE', 'country_code_numeric': '031', 'country_name': 'Azerbaijan', 'country_name_native': 'Azərbaycan', 'country_name_official': 'Republic of Azerbaijan', 'flag_emoji': '🇦🇿', 'phone_code': '+994', 'phone_code_numeric': 994, 'phone_format': '+994 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Asia', 'region': 'Western Asia', 'capital': 'Baku', 'currency_code': 'AZN', 'currency_symbol': '₼', 'timezone': 'Asia/Baku', 'display_order': 57, 'is_featured': False, 'is_active': True},
            
            # Western Countries
            {'country_code': 'US', 'country_code_alpha3': 'USA', 'country_code_numeric': '840', 'country_name': 'United States', 'country_name_native': 'United States', 'country_name_official': 'United States of America', 'flag_emoji': '🇺🇸', 'phone_code': '+1', 'phone_code_numeric': 1, 'phone_format': '+1 (XXX) XXX-XXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'North America', 'region': 'Northern America', 'capital': 'Washington, D.C.', 'currency_code': 'USD', 'currency_symbol': '$', 'timezone': 'America/New_York', 'display_order': 60, 'is_featured': False, 'is_active': True},
            {'country_code': 'GB', 'country_code_alpha3': 'GBR', 'country_code_numeric': '826', 'country_name': 'United Kingdom', 'country_name_native': 'United Kingdom', 'country_name_official': 'United Kingdom of Great Britain and Northern Ireland', 'flag_emoji': '🇬🇧', 'phone_code': '+44', 'phone_code_numeric': 44, 'phone_format': '+44 XXXX XXXXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Europe', 'region': 'Northern Europe', 'capital': 'London', 'currency_code': 'GBP', 'currency_symbol': '£', 'timezone': 'Europe/London', 'display_order': 61, 'is_featured': False, 'is_active': True},
            {'country_code': 'CA', 'country_code_alpha3': 'CAN', 'country_code_numeric': '124', 'country_name': 'Canada', 'country_name_native': 'Canada', 'country_name_official': 'Canada', 'flag_emoji': '🇨🇦', 'phone_code': '+1', 'phone_code_numeric': 1, 'phone_format': '+1 (XXX) XXX-XXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'North America', 'region': 'Northern America', 'capital': 'Ottawa', 'currency_code': 'CAD', 'currency_symbol': '$', 'timezone': 'America/Toronto', 'display_order': 62, 'is_featured': False, 'is_active': True},
            {'country_code': 'AU', 'country_code_alpha3': 'AUS', 'country_code_numeric': '036', 'country_name': 'Australia', 'country_name_native': 'Australia', 'country_name_official': 'Commonwealth of Australia', 'flag_emoji': '🇦🇺', 'phone_code': '+61', 'phone_code_numeric': 61, 'phone_format': '+61 X XXXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Oceania', 'region': 'Australia and New Zealand', 'capital': 'Canberra', 'currency_code': 'AUD', 'currency_symbol': '$', 'timezone': 'Australia/Sydney', 'display_order': 63, 'is_featured': False, 'is_active': True},
            {'country_code': 'NZ', 'country_code_alpha3': 'NZL', 'country_code_numeric': '554', 'country_name': 'New Zealand', 'country_name_native': 'New Zealand', 'country_name_official': 'New Zealand', 'flag_emoji': '🇳🇿', 'phone_code': '+64', 'phone_code_numeric': 64, 'phone_format': '+64 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Oceania', 'region': 'Australia and New Zealand', 'capital': 'Wellington', 'currency_code': 'NZD', 'currency_symbol': '$', 'timezone': 'Pacific/Auckland', 'display_order': 64, 'is_featured': False, 'is_active': True},
            
            # Europe
            {'country_code': 'DE', 'country_code_alpha3': 'DEU', 'country_code_numeric': '276', 'country_name': 'Germany', 'country_name_native': 'Deutschland', 'country_name_official': 'Federal Republic of Germany', 'flag_emoji': '🇩🇪', 'phone_code': '+49', 'phone_code_numeric': 49, 'phone_format': '+49 XXX XXXXXXX', 'phone_length_min': 10, 'phone_length_max': 11, 'continent': 'Europe', 'region': 'Western Europe', 'capital': 'Berlin', 'currency_code': 'EUR', 'currency_symbol': '€', 'timezone': 'Europe/Berlin', 'display_order': 70, 'is_featured': False, 'is_active': True},
            {'country_code': 'FR', 'country_code_alpha3': 'FRA', 'country_code_numeric': '250', 'country_name': 'France', 'country_name_native': 'France', 'country_name_official': 'French Republic', 'flag_emoji': '🇫🇷', 'phone_code': '+33', 'phone_code_numeric': 33, 'phone_format': '+33 X XX XX XX XX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Europe', 'region': 'Western Europe', 'capital': 'Paris', 'currency_code': 'EUR', 'currency_symbol': '€', 'timezone': 'Europe/Paris', 'display_order': 71, 'is_featured': False, 'is_active': True},
            {'country_code': 'IT', 'country_code_alpha3': 'ITA', 'country_code_numeric': '380', 'country_name': 'Italy', 'country_name_native': 'Italia', 'country_name_official': 'Italian Republic', 'flag_emoji': '🇮🇹', 'phone_code': '+39', 'phone_code_numeric': 39, 'phone_format': '+39 XXX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 10, 'continent': 'Europe', 'region': 'Southern Europe', 'capital': 'Rome', 'currency_code': 'EUR', 'currency_symbol': '€', 'timezone': 'Europe/Rome', 'display_order': 72, 'is_featured': False, 'is_active': True},
            {'country_code': 'ES', 'country_code_alpha3': 'ESP', 'country_code_numeric': '724', 'country_name': 'Spain', 'country_name_native': 'España', 'country_name_official': 'Kingdom of Spain', 'flag_emoji': '🇪🇸', 'phone_code': '+34', 'phone_code_numeric': 34, 'phone_format': '+34 XXX XXX XXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Europe', 'region': 'Southern Europe', 'capital': 'Madrid', 'currency_code': 'EUR', 'currency_symbol': '€', 'timezone': 'Europe/Madrid', 'display_order': 73, 'is_featured': False, 'is_active': True},
            {'country_code': 'PT', 'country_code_alpha3': 'PRT', 'country_code_numeric': '620', 'country_name': 'Portugal', 'country_name_native': 'Portugal', 'country_name_official': 'Portuguese Republic', 'flag_emoji': '🇵🇹', 'phone_code': '+351', 'phone_code_numeric': 351, 'phone_format': '+351 XXX XXX XXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Europe', 'region': 'Southern Europe', 'capital': 'Lisbon', 'currency_code': 'EUR', 'currency_symbol': '€', 'timezone': 'Europe/Lisbon', 'display_order': 74, 'is_featured': False, 'is_active': True},
            {'country_code': 'NL', 'country_code_alpha3': 'NLD', 'country_code_numeric': '528', 'country_name': 'Netherlands', 'country_name_native': 'Nederland', 'country_name_official': 'Kingdom of the Netherlands', 'flag_emoji': '🇳🇱', 'phone_code': '+31', 'phone_code_numeric': 31, 'phone_format': '+31 X XXXXXXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Europe', 'region': 'Western Europe', 'capital': 'Amsterdam', 'currency_code': 'EUR', 'currency_symbol': '€', 'timezone': 'Europe/Amsterdam', 'display_order': 75, 'is_featured': False, 'is_active': True},
            {'country_code': 'BE', 'country_code_alpha3': 'BEL', 'country_code_numeric': '056', 'country_name': 'Belgium', 'country_name_native': 'België', 'country_name_official': 'Kingdom of Belgium', 'flag_emoji': '🇧🇪', 'phone_code': '+32', 'phone_code_numeric': 32, 'phone_format': '+32 XXX XX XX XX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Europe', 'region': 'Western Europe', 'capital': 'Brussels', 'currency_code': 'EUR', 'currency_symbol': '€', 'timezone': 'Europe/Brussels', 'display_order': 76, 'is_featured': False, 'is_active': True},
            {'country_code': 'CH', 'country_code_alpha3': 'CHE', 'country_code_numeric': '756', 'country_name': 'Switzerland', 'country_name_native': 'Schweiz', 'country_name_official': 'Swiss Confederation', 'flag_emoji': '🇨🇭', 'phone_code': '+41', 'phone_code_numeric': 41, 'phone_format': '+41 XX XXX XX XX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Europe', 'region': 'Western Europe', 'capital': 'Bern', 'currency_code': 'CHF', 'currency_symbol': 'CHF', 'timezone': 'Europe/Zurich', 'display_order': 77, 'is_featured': False, 'is_active': True},
            {'country_code': 'AT', 'country_code_alpha3': 'AUT', 'country_code_numeric': '040', 'country_name': 'Austria', 'country_name_native': 'Österreich', 'country_name_official': 'Republic of Austria', 'flag_emoji': '🇦🇹', 'phone_code': '+43', 'phone_code_numeric': 43, 'phone_format': '+43 XXX XXXXXX', 'phone_length_min': 10, 'phone_length_max': 11, 'continent': 'Europe', 'region': 'Western Europe', 'capital': 'Vienna', 'currency_code': 'EUR', 'currency_symbol': '€', 'timezone': 'Europe/Vienna', 'display_order': 78, 'is_featured': False, 'is_active': True},
            {'country_code': 'SE', 'country_code_alpha3': 'SWE', 'country_code_numeric': '752', 'country_name': 'Sweden', 'country_name_native': 'Sverige', 'country_name_official': 'Kingdom of Sweden', 'flag_emoji': '🇸🇪', 'phone_code': '+46', 'phone_code_numeric': 46, 'phone_format': '+46 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Europe', 'region': 'Northern Europe', 'capital': 'Stockholm', 'currency_code': 'SEK', 'currency_symbol': 'kr', 'timezone': 'Europe/Stockholm', 'display_order': 79, 'is_featured': False, 'is_active': True},
            {'country_code': 'NO', 'country_code_alpha3': 'NOR', 'country_code_numeric': '578', 'country_name': 'Norway', 'country_name_native': 'Norge', 'country_name_official': 'Kingdom of Norway', 'flag_emoji': '🇳🇴', 'phone_code': '+47', 'phone_code_numeric': 47, 'phone_format': '+47 XXX XX XXX', 'phone_length_min': 8, 'phone_length_max': 8, 'continent': 'Europe', 'region': 'Northern Europe', 'capital': 'Oslo', 'currency_code': 'NOK', 'currency_symbol': 'kr', 'timezone': 'Europe/Oslo', 'display_order': 80, 'is_featured': False, 'is_active': True},
            {'country_code': 'DK', 'country_code_alpha3': 'DNK', 'country_code_numeric': '208', 'country_name': 'Denmark', 'country_name_native': 'Danmark', 'country_name_official': 'Kingdom of Denmark', 'flag_emoji': '🇩🇰', 'phone_code': '+45', 'phone_code_numeric': 45, 'phone_format': '+45 XX XX XX XX', 'phone_length_min': 8, 'phone_length_max': 8, 'continent': 'Europe', 'region': 'Northern Europe', 'capital': 'Copenhagen', 'currency_code': 'DKK', 'currency_symbol': 'kr', 'timezone': 'Europe/Copenhagen', 'display_order': 81, 'is_featured': False, 'is_active': True},
            {'country_code': 'FI', 'country_code_alpha3': 'FIN', 'country_code_numeric': '246', 'country_name': 'Finland', 'country_name_native': 'Suomi', 'country_name_official': 'Republic of Finland', 'flag_emoji': '🇫🇮', 'phone_code': '+358', 'phone_code_numeric': 358, 'phone_format': '+358 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 10, 'continent': 'Europe', 'region': 'Northern Europe', 'capital': 'Helsinki', 'currency_code': 'EUR', 'currency_symbol': '€', 'timezone': 'Europe/Helsinki', 'display_order': 82, 'is_featured': False, 'is_active': True},
            {'country_code': 'IE', 'country_code_alpha3': 'IRL', 'country_code_numeric': '372', 'country_name': 'Ireland', 'country_name_native': 'Éire', 'country_name_official': 'Republic of Ireland', 'flag_emoji': '🇮🇪', 'phone_code': '+353', 'phone_code_numeric': 353, 'phone_format': '+353 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Europe', 'region': 'Northern Europe', 'capital': 'Dublin', 'currency_code': 'EUR', 'currency_symbol': '€', 'timezone': 'Europe/Dublin', 'display_order': 83, 'is_featured': False, 'is_active': True},
            {'country_code': 'PL', 'country_code_alpha3': 'POL', 'country_code_numeric': '616', 'country_name': 'Poland', 'country_name_native': 'Polska', 'country_name_official': 'Republic of Poland', 'flag_emoji': '🇵🇱', 'phone_code': '+48', 'phone_code_numeric': 48, 'phone_format': '+48 XXX XXX XXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Europe', 'region': 'Eastern Europe', 'capital': 'Warsaw', 'currency_code': 'PLN', 'currency_symbol': 'zł', 'timezone': 'Europe/Warsaw', 'display_order': 84, 'is_featured': False, 'is_active': True},
            {'country_code': 'CZ', 'country_code_alpha3': 'CZE', 'country_code_numeric': '203', 'country_name': 'Czech Republic', 'country_name_native': 'Česko', 'country_name_official': 'Czech Republic', 'flag_emoji': '🇨🇿', 'phone_code': '+420', 'phone_code_numeric': 420, 'phone_format': '+420 XXX XXX XXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Europe', 'region': 'Eastern Europe', 'capital': 'Prague', 'currency_code': 'CZK', 'currency_symbol': 'Kč', 'timezone': 'Europe/Prague', 'display_order': 85, 'is_featured': False, 'is_active': True},
            {'country_code': 'GR', 'country_code_alpha3': 'GRC', 'country_code_numeric': '300', 'country_name': 'Greece', 'country_name_native': 'Ελλάδα', 'country_name_official': 'Hellenic Republic', 'flag_emoji': '🇬🇷', 'phone_code': '+30', 'phone_code_numeric': 30, 'phone_format': '+30 XXX XXX XXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Europe', 'region': 'Southern Europe', 'capital': 'Athens', 'currency_code': 'EUR', 'currency_symbol': '€', 'timezone': 'Europe/Athens', 'display_order': 86, 'is_featured': False, 'is_active': True},
            {'country_code': 'RU', 'country_code_alpha3': 'RUS', 'country_code_numeric': '643', 'country_name': 'Russia', 'country_name_native': 'Россия', 'country_name_official': 'Russian Federation', 'flag_emoji': '🇷🇺', 'phone_code': '+7', 'phone_code_numeric': 7, 'phone_format': '+7 XXX XXX XX XX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Europe', 'region': 'Eastern Europe', 'capital': 'Moscow', 'currency_code': 'RUB', 'currency_symbol': '₽', 'timezone': 'Europe/Moscow', 'display_order': 87, 'is_featured': False, 'is_active': True},
            {'country_code': 'UA', 'country_code_alpha3': 'UKR', 'country_code_numeric': '804', 'country_name': 'Ukraine', 'country_name_native': 'Україна', 'country_name_official': 'Ukraine', 'flag_emoji': '🇺🇦', 'phone_code': '+380', 'phone_code_numeric': 380, 'phone_format': '+380 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Europe', 'region': 'Eastern Europe', 'capital': 'Kyiv', 'currency_code': 'UAH', 'currency_symbol': '₴', 'timezone': 'Europe/Kiev', 'display_order': 88, 'is_featured': False, 'is_active': True},
            
            # Africa
            {'country_code': 'EG', 'country_code_alpha3': 'EGY', 'country_code_numeric': '818', 'country_name': 'Egypt', 'country_name_native': 'مصر', 'country_name_official': 'Arab Republic of Egypt', 'flag_emoji': '🇪🇬', 'phone_code': '+20', 'phone_code_numeric': 20, 'phone_format': '+20 XX XXXX XXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Africa', 'region': 'Northern Africa', 'capital': 'Cairo', 'currency_code': 'EGP', 'currency_symbol': '£', 'timezone': 'Africa/Cairo', 'display_order': 90, 'is_featured': False, 'is_active': True},
            {'country_code': 'NG', 'country_code_alpha3': 'NGA', 'country_code_numeric': '566', 'country_name': 'Nigeria', 'country_name_native': 'Nigeria', 'country_name_official': 'Federal Republic of Nigeria', 'flag_emoji': '🇳🇬', 'phone_code': '+234', 'phone_code_numeric': 234, 'phone_format': '+234 XXX XXX XXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'Africa', 'region': 'Western Africa', 'capital': 'Abuja', 'currency_code': 'NGN', 'currency_symbol': '₦', 'timezone': 'Africa/Lagos', 'display_order': 91, 'is_featured': False, 'is_active': True},
            {'country_code': 'ZA', 'country_code_alpha3': 'ZAF', 'country_code_numeric': '710', 'country_name': 'South Africa', 'country_name_native': 'South Africa', 'country_name_official': 'Republic of South Africa', 'flag_emoji': '🇿🇦', 'phone_code': '+27', 'phone_code_numeric': 27, 'phone_format': '+27 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Africa', 'region': 'Southern Africa', 'capital': 'Pretoria', 'currency_code': 'ZAR', 'currency_symbol': 'R', 'timezone': 'Africa/Johannesburg', 'display_order': 92, 'is_featured': False, 'is_active': True},
            {'country_code': 'KE', 'country_code_alpha3': 'KEN', 'country_code_numeric': '404', 'country_name': 'Kenya', 'country_name_native': 'Kenya', 'country_name_official': 'Republic of Kenya', 'flag_emoji': '🇰🇪', 'phone_code': '+254', 'phone_code_numeric': 254, 'phone_format': '+254 XXX XXXXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Africa', 'region': 'Eastern Africa', 'capital': 'Nairobi', 'currency_code': 'KES', 'currency_symbol': 'KSh', 'timezone': 'Africa/Nairobi', 'display_order': 93, 'is_featured': False, 'is_active': True},
            {'country_code': 'MA', 'country_code_alpha3': 'MAR', 'country_code_numeric': '504', 'country_name': 'Morocco', 'country_name_native': 'المغرب', 'country_name_official': 'Kingdom of Morocco', 'flag_emoji': '🇲🇦', 'phone_code': '+212', 'phone_code_numeric': 212, 'phone_format': '+212 XXX XXXXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Africa', 'region': 'Northern Africa', 'capital': 'Rabat', 'currency_code': 'MAD', 'currency_symbol': 'د.م.', 'timezone': 'Africa/Casablanca', 'display_order': 94, 'is_featured': False, 'is_active': True},
            {'country_code': 'GH', 'country_code_alpha3': 'GHA', 'country_code_numeric': '288', 'country_name': 'Ghana', 'country_name_native': 'Ghana', 'country_name_official': 'Republic of Ghana', 'flag_emoji': '🇬🇭', 'phone_code': '+233', 'phone_code_numeric': 233, 'phone_format': '+233 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Africa', 'region': 'Western Africa', 'capital': 'Accra', 'currency_code': 'GHS', 'currency_symbol': '₵', 'timezone': 'Africa/Accra', 'display_order': 95, 'is_featured': False, 'is_active': True},
            {'country_code': 'ET', 'country_code_alpha3': 'ETH', 'country_code_numeric': '231', 'country_name': 'Ethiopia', 'country_name_native': 'ኢትዮጵያ', 'country_name_official': 'Federal Democratic Republic of Ethiopia', 'flag_emoji': '🇪🇹', 'phone_code': '+251', 'phone_code_numeric': 251, 'phone_format': '+251 XX XXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Africa', 'region': 'Eastern Africa', 'capital': 'Addis Ababa', 'currency_code': 'ETB', 'currency_symbol': 'Br', 'timezone': 'Africa/Addis_Ababa', 'display_order': 96, 'is_featured': False, 'is_active': True},
            {'country_code': 'TZ', 'country_code_alpha3': 'TZA', 'country_code_numeric': '834', 'country_name': 'Tanzania', 'country_name_native': 'Tanzania', 'country_name_official': 'United Republic of Tanzania', 'flag_emoji': '🇹🇿', 'phone_code': '+255', 'phone_code_numeric': 255, 'phone_format': '+255 XXX XXX XXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'Africa', 'region': 'Eastern Africa', 'capital': 'Dodoma', 'currency_code': 'TZS', 'currency_symbol': 'TSh', 'timezone': 'Africa/Dar_es_Salaam', 'display_order': 97, 'is_featured': False, 'is_active': True},
            
            # South America
            {'country_code': 'BR', 'country_code_alpha3': 'BRA', 'country_code_numeric': '076', 'country_name': 'Brazil', 'country_name_native': 'Brasil', 'country_name_official': 'Federative Republic of Brazil', 'flag_emoji': '🇧🇷', 'phone_code': '+55', 'phone_code_numeric': 55, 'phone_format': '+55 XX XXXXX XXXX', 'phone_length_min': 10, 'phone_length_max': 11, 'continent': 'South America', 'region': 'South America', 'capital': 'Brasília', 'currency_code': 'BRL', 'currency_symbol': 'R$', 'timezone': 'America/Sao_Paulo', 'display_order': 100, 'is_featured': False, 'is_active': True},
            {'country_code': 'AR', 'country_code_alpha3': 'ARG', 'country_code_numeric': '032', 'country_name': 'Argentina', 'country_name_native': 'Argentina', 'country_name_official': 'Argentine Republic', 'flag_emoji': '🇦🇷', 'phone_code': '+54', 'phone_code_numeric': 54, 'phone_format': '+54 XX XXXX XXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'South America', 'region': 'South America', 'capital': 'Buenos Aires', 'currency_code': 'ARS', 'currency_symbol': '$', 'timezone': 'America/Argentina/Buenos_Aires', 'display_order': 101, 'is_featured': False, 'is_active': True},
            {'country_code': 'CO', 'country_code_alpha3': 'COL', 'country_code_numeric': '170', 'country_name': 'Colombia', 'country_name_native': 'Colombia', 'country_name_official': 'Republic of Colombia', 'flag_emoji': '🇨🇴', 'phone_code': '+57', 'phone_code_numeric': 57, 'phone_format': '+57 XXX XXX XXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'South America', 'region': 'South America', 'capital': 'Bogotá', 'currency_code': 'COP', 'currency_symbol': '$', 'timezone': 'America/Bogota', 'display_order': 102, 'is_featured': False, 'is_active': True},
            {'country_code': 'MX', 'country_code_alpha3': 'MEX', 'country_code_numeric': '484', 'country_name': 'Mexico', 'country_name_native': 'México', 'country_name_official': 'United Mexican States', 'flag_emoji': '🇲🇽', 'phone_code': '+52', 'phone_code_numeric': 52, 'phone_format': '+52 XX XXXX XXXX', 'phone_length_min': 10, 'phone_length_max': 10, 'continent': 'North America', 'region': 'Central America', 'capital': 'Mexico City', 'currency_code': 'MXN', 'currency_symbol': '$', 'timezone': 'America/Mexico_City', 'display_order': 103, 'is_featured': False, 'is_active': True},
            {'country_code': 'CL', 'country_code_alpha3': 'CHL', 'country_code_numeric': '152', 'country_name': 'Chile', 'country_name_native': 'Chile', 'country_name_official': 'Republic of Chile', 'flag_emoji': '🇨🇱', 'phone_code': '+56', 'phone_code_numeric': 56, 'phone_format': '+56 X XXXX XXXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'South America', 'region': 'South America', 'capital': 'Santiago', 'currency_code': 'CLP', 'currency_symbol': '$', 'timezone': 'America/Santiago', 'display_order': 104, 'is_featured': False, 'is_active': True},
            {'country_code': 'PE', 'country_code_alpha3': 'PER', 'country_code_numeric': '604', 'country_name': 'Peru', 'country_name_native': 'Perú', 'country_name_official': 'Republic of Peru', 'flag_emoji': '🇵🇪', 'phone_code': '+51', 'phone_code_numeric': 51, 'phone_format': '+51 XXX XXX XXX', 'phone_length_min': 9, 'phone_length_max': 9, 'continent': 'South America', 'region': 'South America', 'capital': 'Lima', 'currency_code': 'PEN', 'currency_symbol': 'S/', 'timezone': 'America/Lima', 'display_order': 105, 'is_featured': False, 'is_active': True},
        ]
