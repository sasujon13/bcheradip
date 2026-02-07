"""
Insert ALL Countries Script
---------------------------
Complete list of all 195+ countries with full data.
"""

import pymysql

DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '',
    'database': 'cheradip_cheradip',
    'charset': 'utf8mb4'
}

INSERT_SQL = """
INSERT INTO `cheradip_country` (
    `country_code`, `country_code_alpha3`, `country_code_numeric`, 
    `country_name`, `country_name_native`, `country_name_official`,
    `flag_emoji`, `phone_code`, `phone_code_numeric`, `phone_format`,
    `phone_length_min`, `phone_length_max`, `continent`, `region`,
    `capital`, `currency_code`, `currency_symbol`, `timezone`,
    `display_order`, `is_featured`, `is_active`
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
) ON DUPLICATE KEY UPDATE
    `country_name` = VALUES(`country_name`),
    `country_name_native` = VALUES(`country_name_native`),
    `country_name_official` = VALUES(`country_name_official`),
    `flag_emoji` = VALUES(`flag_emoji`),
    `phone_code` = VALUES(`phone_code`),
    `phone_code_numeric` = VALUES(`phone_code_numeric`),
    `phone_format` = VALUES(`phone_format`),
    `phone_length_min` = VALUES(`phone_length_min`),
    `phone_length_max` = VALUES(`phone_length_max`),
    `continent` = VALUES(`continent`),
    `region` = VALUES(`region`),
    `capital` = VALUES(`capital`),
    `currency_code` = VALUES(`currency_code`),
    `currency_symbol` = VALUES(`currency_symbol`),
    `timezone` = VALUES(`timezone`),
    `display_order` = VALUES(`display_order`),
    `is_featured` = VALUES(`is_featured`),
    `is_active` = VALUES(`is_active`)
"""

# Complete list of all countries
# Format: (code, alpha3, numeric, name, native, official, emoji, phone, phone_num, format, min, max, continent, region, capital, currency, symbol, timezone, order, featured, active)
COUNTRIES = [
    # ============== SOUTH ASIA (Featured) ==============
    ('BD', 'BGD', '050', 'Bangladesh', 'বাংলাদেশ', "People's Republic of Bangladesh", '🇧🇩', '+880', 880, '+880 1XXX-XXXXXX', 10, 10, 'Asia', 'Southern Asia', 'Dhaka', 'BDT', '৳', 'Asia/Dhaka', 1, 1, 1),
    ('IN', 'IND', '356', 'India', 'भारत', 'Republic of India', '🇮🇳', '+91', 91, '+91 XXXXX XXXXX', 10, 10, 'Asia', 'Southern Asia', 'New Delhi', 'INR', '₹', 'Asia/Kolkata', 2, 1, 1),
    ('PK', 'PAK', '586', 'Pakistan', 'پاکستان', 'Islamic Republic of Pakistan', '🇵🇰', '+92', 92, '+92 XXX XXXXXXX', 10, 10, 'Asia', 'Southern Asia', 'Islamabad', 'PKR', '₨', 'Asia/Karachi', 3, 1, 1),
    ('NP', 'NPL', '524', 'Nepal', 'नेपाल', 'Federal Democratic Republic of Nepal', '🇳🇵', '+977', 977, '+977 XX XXXXXXXX', 10, 10, 'Asia', 'Southern Asia', 'Kathmandu', 'NPR', '₨', 'Asia/Kathmandu', 4, 1, 1),
    ('LK', 'LKA', '144', 'Sri Lanka', 'ශ්‍රී ලංකාව', 'Democratic Socialist Republic of Sri Lanka', '🇱🇰', '+94', 94, '+94 XX XXX XXXX', 9, 9, 'Asia', 'Southern Asia', 'Sri Jayawardenepura Kotte', 'LKR', 'Rs', 'Asia/Colombo', 5, 1, 1),
    ('BT', 'BTN', '064', 'Bhutan', 'འབྲུག་རྒྱལ་ཁབ་', 'Kingdom of Bhutan', '🇧🇹', '+975', 975, '+975 XX XXX XXX', 8, 8, 'Asia', 'Southern Asia', 'Thimphu', 'BTN', 'Nu.', 'Asia/Thimphu', 6, 0, 1),
    ('MV', 'MDV', '462', 'Maldives', 'ދިވެހިރާއްޖެ', 'Republic of Maldives', '🇲🇻', '+960', 960, '+960 XXX XXXX', 7, 7, 'Asia', 'Southern Asia', 'Malé', 'MVR', 'Rf', 'Indian/Maldives', 7, 0, 1),
    ('AF', 'AFG', '004', 'Afghanistan', 'افغانستان', 'Islamic Republic of Afghanistan', '🇦🇫', '+93', 93, '+93 XX XXX XXXX', 9, 9, 'Asia', 'Southern Asia', 'Kabul', 'AFN', '؋', 'Asia/Kabul', 8, 0, 1),
    
    # ============== MIDDLE EAST (Featured) ==============
    ('AE', 'ARE', '784', 'United Arab Emirates', 'الإمارات العربية المتحدة', 'United Arab Emirates', '🇦🇪', '+971', 971, '+971 XX XXX XXXX', 9, 9, 'Asia', 'Western Asia', 'Abu Dhabi', 'AED', 'د.إ', 'Asia/Dubai', 10, 1, 1),
    ('SA', 'SAU', '682', 'Saudi Arabia', 'المملكة العربية السعودية', 'Kingdom of Saudi Arabia', '🇸🇦', '+966', 966, '+966 X XXX XXXX', 9, 9, 'Asia', 'Western Asia', 'Riyadh', 'SAR', '﷼', 'Asia/Riyadh', 11, 1, 1),
    ('QA', 'QAT', '634', 'Qatar', 'قطر', 'State of Qatar', '🇶🇦', '+974', 974, '+974 XXXX XXXX', 8, 8, 'Asia', 'Western Asia', 'Doha', 'QAR', '﷼', 'Asia/Qatar', 12, 1, 1),
    ('KW', 'KWT', '414', 'Kuwait', 'الكويت', 'State of Kuwait', '🇰🇼', '+965', 965, '+965 XXXX XXXX', 8, 8, 'Asia', 'Western Asia', 'Kuwait City', 'KWD', 'د.ك', 'Asia/Kuwait', 13, 0, 1),
    ('BH', 'BHR', '048', 'Bahrain', 'البحرين', 'Kingdom of Bahrain', '🇧🇭', '+973', 973, '+973 XXXX XXXX', 8, 8, 'Asia', 'Western Asia', 'Manama', 'BHD', '.د.ب', 'Asia/Bahrain', 14, 0, 1),
    ('OM', 'OMN', '512', 'Oman', 'عمان', 'Sultanate of Oman', '🇴🇲', '+968', 968, '+968 XXXX XXXX', 8, 8, 'Asia', 'Western Asia', 'Muscat', 'OMR', '﷼', 'Asia/Muscat', 15, 0, 1),
    ('YE', 'YEM', '887', 'Yemen', 'اليمن', 'Republic of Yemen', '🇾🇪', '+967', 967, '+967 XXX XXX XXX', 9, 9, 'Asia', 'Western Asia', "Sana'a", 'YER', '﷼', 'Asia/Aden', 16, 0, 1),
    ('IR', 'IRN', '364', 'Iran', 'ایران', 'Islamic Republic of Iran', '🇮🇷', '+98', 98, '+98 XXX XXX XXXX', 10, 10, 'Asia', 'Southern Asia', 'Tehran', 'IRR', '﷼', 'Asia/Tehran', 17, 0, 1),
    ('IQ', 'IRQ', '368', 'Iraq', 'العراق', 'Republic of Iraq', '🇮🇶', '+964', 964, '+964 XXX XXX XXXX', 10, 10, 'Asia', 'Western Asia', 'Baghdad', 'IQD', 'ع.د', 'Asia/Baghdad', 18, 0, 1),
    ('JO', 'JOR', '400', 'Jordan', 'الأردن', 'Hashemite Kingdom of Jordan', '🇯🇴', '+962', 962, '+962 X XXXX XXXX', 9, 9, 'Asia', 'Western Asia', 'Amman', 'JOD', 'د.ا', 'Asia/Amman', 19, 0, 1),
    ('LB', 'LBN', '422', 'Lebanon', 'لبنان', 'Lebanese Republic', '🇱🇧', '+961', 961, '+961 XX XXX XXX', 8, 8, 'Asia', 'Western Asia', 'Beirut', 'LBP', 'ل.ل', 'Asia/Beirut', 20, 0, 1),
    ('SY', 'SYR', '760', 'Syria', 'سوريا', 'Syrian Arab Republic', '🇸🇾', '+963', 963, '+963 XXX XXX XXX', 9, 9, 'Asia', 'Western Asia', 'Damascus', 'SYP', '£', 'Asia/Damascus', 21, 0, 1),
    ('PS', 'PSE', '275', 'Palestine', 'فلسطين', 'State of Palestine', '🇵🇸', '+970', 970, '+970 XX XXX XXXX', 9, 9, 'Asia', 'Western Asia', 'Ramallah', 'ILS', '₪', 'Asia/Gaza', 22, 0, 1),
    ('IL', 'ISR', '376', 'Israel', 'ישראל', 'State of Israel', '🇮🇱', '+972', 972, '+972 XX XXX XXXX', 9, 9, 'Asia', 'Western Asia', 'Jerusalem', 'ILS', '₪', 'Asia/Jerusalem', 23, 0, 1),
    ('TR', 'TUR', '792', 'Turkey', 'Türkiye', 'Republic of Turkey', '🇹🇷', '+90', 90, '+90 XXX XXX XXXX', 10, 10, 'Asia', 'Western Asia', 'Ankara', 'TRY', '₺', 'Europe/Istanbul', 24, 0, 1),
    ('CY', 'CYP', '196', 'Cyprus', 'Κύπρος', 'Republic of Cyprus', '🇨🇾', '+357', 357, '+357 XX XXXXXX', 8, 8, 'Asia', 'Western Asia', 'Nicosia', 'EUR', '€', 'Asia/Nicosia', 25, 0, 1),
    
    # ============== SOUTHEAST ASIA ==============
    ('MY', 'MYS', '458', 'Malaysia', 'Malaysia', 'Malaysia', '🇲🇾', '+60', 60, '+60 XX XXX XXXX', 9, 10, 'Asia', 'South-Eastern Asia', 'Kuala Lumpur', 'MYR', 'RM', 'Asia/Kuala_Lumpur', 30, 1, 1),
    ('SG', 'SGP', '702', 'Singapore', 'Singapore', 'Republic of Singapore', '🇸🇬', '+65', 65, '+65 XXXX XXXX', 8, 8, 'Asia', 'South-Eastern Asia', 'Singapore', 'SGD', '$', 'Asia/Singapore', 31, 0, 1),
    ('ID', 'IDN', '360', 'Indonesia', 'Indonesia', 'Republic of Indonesia', '🇮🇩', '+62', 62, '+62 XXX XXXX XXXX', 10, 12, 'Asia', 'South-Eastern Asia', 'Jakarta', 'IDR', 'Rp', 'Asia/Jakarta', 32, 0, 1),
    ('TH', 'THA', '764', 'Thailand', 'ประเทศไทย', 'Kingdom of Thailand', '🇹🇭', '+66', 66, '+66 XX XXX XXXX', 9, 9, 'Asia', 'South-Eastern Asia', 'Bangkok', 'THB', '฿', 'Asia/Bangkok', 33, 0, 1),
    ('PH', 'PHL', '608', 'Philippines', 'Pilipinas', 'Republic of the Philippines', '🇵🇭', '+63', 63, '+63 XXX XXX XXXX', 10, 10, 'Asia', 'South-Eastern Asia', 'Manila', 'PHP', '₱', 'Asia/Manila', 34, 0, 1),
    ('VN', 'VNM', '704', 'Vietnam', 'Việt Nam', 'Socialist Republic of Vietnam', '🇻🇳', '+84', 84, '+84 XXX XXX XXXX', 9, 10, 'Asia', 'South-Eastern Asia', 'Hanoi', 'VND', '₫', 'Asia/Ho_Chi_Minh', 35, 0, 1),
    ('MM', 'MMR', '104', 'Myanmar', 'မြန်မာ', 'Republic of the Union of Myanmar', '🇲🇲', '+95', 95, '+95 XX XXX XXXX', 9, 10, 'Asia', 'South-Eastern Asia', 'Naypyidaw', 'MMK', 'K', 'Asia/Yangon', 36, 0, 1),
    ('KH', 'KHM', '116', 'Cambodia', 'កម្ពុជា', 'Kingdom of Cambodia', '🇰🇭', '+855', 855, '+855 XX XXX XXXX', 9, 9, 'Asia', 'South-Eastern Asia', 'Phnom Penh', 'KHR', '៛', 'Asia/Phnom_Penh', 37, 0, 1),
    ('LA', 'LAO', '418', 'Laos', 'ລາວ', "Lao People's Democratic Republic", '🇱🇦', '+856', 856, '+856 XX XX XXX XXX', 10, 10, 'Asia', 'South-Eastern Asia', 'Vientiane', 'LAK', '₭', 'Asia/Vientiane', 38, 0, 1),
    ('BN', 'BRN', '096', 'Brunei', 'Brunei', 'Nation of Brunei', '🇧🇳', '+673', 673, '+673 XXX XXXX', 7, 7, 'Asia', 'South-Eastern Asia', 'Bandar Seri Begawan', 'BND', '$', 'Asia/Brunei', 39, 0, 1),
    ('TL', 'TLS', '626', 'Timor-Leste', 'Timor-Leste', 'Democratic Republic of Timor-Leste', '🇹🇱', '+670', 670, '+670 XXX XXXX', 7, 8, 'Asia', 'South-Eastern Asia', 'Dili', 'USD', '$', 'Asia/Dili', 40, 0, 1),
    
    # ============== EAST ASIA ==============
    ('CN', 'CHN', '156', 'China', '中国', "People's Republic of China", '🇨🇳', '+86', 86, '+86 XXX XXXX XXXX', 11, 11, 'Asia', 'Eastern Asia', 'Beijing', 'CNY', '¥', 'Asia/Shanghai', 45, 0, 1),
    ('JP', 'JPN', '392', 'Japan', '日本', 'Japan', '🇯🇵', '+81', 81, '+81 XX XXXX XXXX', 10, 10, 'Asia', 'Eastern Asia', 'Tokyo', 'JPY', '¥', 'Asia/Tokyo', 46, 0, 1),
    ('KR', 'KOR', '410', 'South Korea', '대한민국', 'Republic of Korea', '🇰🇷', '+82', 82, '+82 XX XXXX XXXX', 9, 10, 'Asia', 'Eastern Asia', 'Seoul', 'KRW', '₩', 'Asia/Seoul', 47, 0, 1),
    ('KP', 'PRK', '408', 'North Korea', '북한', "Democratic People's Republic of Korea", '🇰🇵', '+850', 850, '+850 XXX XXX XXXX', 10, 10, 'Asia', 'Eastern Asia', 'Pyongyang', 'KPW', '₩', 'Asia/Pyongyang', 48, 0, 1),
    ('TW', 'TWN', '158', 'Taiwan', '台灣', 'Republic of China', '🇹🇼', '+886', 886, '+886 XXX XXX XXX', 9, 9, 'Asia', 'Eastern Asia', 'Taipei', 'TWD', 'NT$', 'Asia/Taipei', 49, 0, 1),
    ('HK', 'HKG', '344', 'Hong Kong', '香港', 'Hong Kong Special Administrative Region', '🇭🇰', '+852', 852, '+852 XXXX XXXX', 8, 8, 'Asia', 'Eastern Asia', 'Hong Kong', 'HKD', '$', 'Asia/Hong_Kong', 50, 0, 1),
    ('MO', 'MAC', '446', 'Macau', '澳門', 'Macao Special Administrative Region', '🇲🇴', '+853', 853, '+853 XXXX XXXX', 8, 8, 'Asia', 'Eastern Asia', 'Macau', 'MOP', 'MOP$', 'Asia/Macau', 51, 0, 1),
    ('MN', 'MNG', '496', 'Mongolia', 'Монгол', 'Mongolia', '🇲🇳', '+976', 976, '+976 XX XX XXXX', 8, 8, 'Asia', 'Eastern Asia', 'Ulaanbaatar', 'MNT', '₮', 'Asia/Ulaanbaatar', 52, 0, 1),
    
    # ============== CENTRAL ASIA ==============
    ('KZ', 'KAZ', '398', 'Kazakhstan', 'Қазақстан', 'Republic of Kazakhstan', '🇰🇿', '+7', 7, '+7 XXX XXX XX XX', 10, 10, 'Asia', 'Central Asia', 'Astana', 'KZT', '₸', 'Asia/Almaty', 55, 0, 1),
    ('UZ', 'UZB', '860', 'Uzbekistan', "O'zbekiston", 'Republic of Uzbekistan', '🇺🇿', '+998', 998, '+998 XX XXX XXXX', 9, 9, 'Asia', 'Central Asia', 'Tashkent', 'UZS', "so'm", 'Asia/Tashkent', 56, 0, 1),
    ('TM', 'TKM', '795', 'Turkmenistan', 'Türkmenistan', 'Turkmenistan', '🇹🇲', '+993', 993, '+993 XX XXXXXX', 8, 8, 'Asia', 'Central Asia', 'Ashgabat', 'TMT', 'm', 'Asia/Ashgabat', 57, 0, 1),
    ('KG', 'KGZ', '417', 'Kyrgyzstan', 'Кыргызстан', 'Kyrgyz Republic', '🇰🇬', '+996', 996, '+996 XXX XXXXXX', 9, 9, 'Asia', 'Central Asia', 'Bishkek', 'KGS', 'с', 'Asia/Bishkek', 58, 0, 1),
    ('TJ', 'TJK', '762', 'Tajikistan', 'Тоҷикистон', 'Republic of Tajikistan', '🇹🇯', '+992', 992, '+992 XX XXX XXXX', 9, 9, 'Asia', 'Central Asia', 'Dushanbe', 'TJS', 'SM', 'Asia/Dushanbe', 59, 0, 1),
    
    # ============== CAUCASUS ==============
    ('GE', 'GEO', '268', 'Georgia', 'საქართველო', 'Georgia', '🇬🇪', '+995', 995, '+995 XXX XX XX XX', 9, 9, 'Asia', 'Western Asia', 'Tbilisi', 'GEL', '₾', 'Asia/Tbilisi', 60, 0, 1),
    ('AM', 'ARM', '051', 'Armenia', 'Հdelays', 'Republic of Armenia', '🇦🇲', '+374', 374, '+374 XX XXXXXX', 8, 8, 'Asia', 'Western Asia', 'Yerevan', 'AMD', '֏', 'Asia/Yerevan', 61, 0, 1),
    ('AZ', 'AZE', '031', 'Azerbaijan', 'Azərbaycan', 'Republic of Azerbaijan', '🇦🇿', '+994', 994, '+994 XX XXX XXXX', 9, 9, 'Asia', 'Western Asia', 'Baku', 'AZN', '₼', 'Asia/Baku', 62, 0, 1),
    
    # ============== EUROPE - WESTERN ==============
    ('GB', 'GBR', '826', 'United Kingdom', 'United Kingdom', 'United Kingdom of Great Britain and Northern Ireland', '🇬🇧', '+44', 44, '+44 XXXX XXXXXX', 10, 10, 'Europe', 'Northern Europe', 'London', 'GBP', '£', 'Europe/London', 70, 0, 1),
    ('DE', 'DEU', '276', 'Germany', 'Deutschland', 'Federal Republic of Germany', '🇩🇪', '+49', 49, '+49 XXX XXXXXXX', 10, 11, 'Europe', 'Western Europe', 'Berlin', 'EUR', '€', 'Europe/Berlin', 71, 0, 1),
    ('FR', 'FRA', '250', 'France', 'France', 'French Republic', '🇫🇷', '+33', 33, '+33 X XX XX XX XX', 9, 9, 'Europe', 'Western Europe', 'Paris', 'EUR', '€', 'Europe/Paris', 72, 0, 1),
    ('IT', 'ITA', '380', 'Italy', 'Italia', 'Italian Republic', '🇮🇹', '+39', 39, '+39 XXX XXX XXXX', 9, 10, 'Europe', 'Southern Europe', 'Rome', 'EUR', '€', 'Europe/Rome', 73, 0, 1),
    ('ES', 'ESP', '724', 'Spain', 'España', 'Kingdom of Spain', '🇪🇸', '+34', 34, '+34 XXX XXX XXX', 9, 9, 'Europe', 'Southern Europe', 'Madrid', 'EUR', '€', 'Europe/Madrid', 74, 0, 1),
    ('PT', 'PRT', '620', 'Portugal', 'Portugal', 'Portuguese Republic', '🇵🇹', '+351', 351, '+351 XXX XXX XXX', 9, 9, 'Europe', 'Southern Europe', 'Lisbon', 'EUR', '€', 'Europe/Lisbon', 75, 0, 1),
    ('NL', 'NLD', '528', 'Netherlands', 'Nederland', 'Kingdom of the Netherlands', '🇳🇱', '+31', 31, '+31 X XXXXXXXX', 9, 9, 'Europe', 'Western Europe', 'Amsterdam', 'EUR', '€', 'Europe/Amsterdam', 76, 0, 1),
    ('BE', 'BEL', '056', 'Belgium', 'België', 'Kingdom of Belgium', '🇧🇪', '+32', 32, '+32 XXX XX XX XX', 9, 9, 'Europe', 'Western Europe', 'Brussels', 'EUR', '€', 'Europe/Brussels', 77, 0, 1),
    ('CH', 'CHE', '756', 'Switzerland', 'Schweiz', 'Swiss Confederation', '🇨🇭', '+41', 41, '+41 XX XXX XX XX', 9, 9, 'Europe', 'Western Europe', 'Bern', 'CHF', 'CHF', 'Europe/Zurich', 78, 0, 1),
    ('AT', 'AUT', '040', 'Austria', 'Österreich', 'Republic of Austria', '🇦🇹', '+43', 43, '+43 XXX XXXXXX', 10, 11, 'Europe', 'Western Europe', 'Vienna', 'EUR', '€', 'Europe/Vienna', 79, 0, 1),
    ('LU', 'LUX', '442', 'Luxembourg', 'Luxembourg', 'Grand Duchy of Luxembourg', '🇱🇺', '+352', 352, '+352 XXX XXX XXX', 9, 9, 'Europe', 'Western Europe', 'Luxembourg', 'EUR', '€', 'Europe/Luxembourg', 80, 0, 1),
    ('LI', 'LIE', '438', 'Liechtenstein', 'Liechtenstein', 'Principality of Liechtenstein', '🇱🇮', '+423', 423, '+423 XXX XXXX', 7, 7, 'Europe', 'Western Europe', 'Vaduz', 'CHF', 'CHF', 'Europe/Vaduz', 81, 0, 1),
    ('MC', 'MCO', '492', 'Monaco', 'Monaco', 'Principality of Monaco', '🇲🇨', '+377', 377, '+377 XX XX XX XX', 8, 8, 'Europe', 'Western Europe', 'Monaco', 'EUR', '€', 'Europe/Monaco', 82, 0, 1),
    ('AD', 'AND', '020', 'Andorra', 'Andorra', 'Principality of Andorra', '🇦🇩', '+376', 376, '+376 XXX XXX', 6, 6, 'Europe', 'Southern Europe', 'Andorra la Vella', 'EUR', '€', 'Europe/Andorra', 83, 0, 1),
    ('SM', 'SMR', '674', 'San Marino', 'San Marino', 'Republic of San Marino', '🇸🇲', '+378', 378, '+378 XXXX XXXXXX', 10, 10, 'Europe', 'Southern Europe', 'San Marino', 'EUR', '€', 'Europe/San_Marino', 84, 0, 1),
    ('VA', 'VAT', '336', 'Vatican City', 'Città del Vaticano', 'Vatican City State', '🇻🇦', '+379', 379, '+379 XX XXXX XXXX', 10, 10, 'Europe', 'Southern Europe', 'Vatican City', 'EUR', '€', 'Europe/Vatican', 85, 0, 1),
    ('MT', 'MLT', '470', 'Malta', 'Malta', 'Republic of Malta', '🇲🇹', '+356', 356, '+356 XXXX XXXX', 8, 8, 'Europe', 'Southern Europe', 'Valletta', 'EUR', '€', 'Europe/Malta', 86, 0, 1),
    
    # ============== EUROPE - NORTHERN ==============
    ('SE', 'SWE', '752', 'Sweden', 'Sverige', 'Kingdom of Sweden', '🇸🇪', '+46', 46, '+46 XX XXX XXXX', 9, 9, 'Europe', 'Northern Europe', 'Stockholm', 'SEK', 'kr', 'Europe/Stockholm', 90, 0, 1),
    ('NO', 'NOR', '578', 'Norway', 'Norge', 'Kingdom of Norway', '🇳🇴', '+47', 47, '+47 XXX XX XXX', 8, 8, 'Europe', 'Northern Europe', 'Oslo', 'NOK', 'kr', 'Europe/Oslo', 91, 0, 1),
    ('DK', 'DNK', '208', 'Denmark', 'Danmark', 'Kingdom of Denmark', '🇩🇰', '+45', 45, '+45 XX XX XX XX', 8, 8, 'Europe', 'Northern Europe', 'Copenhagen', 'DKK', 'kr', 'Europe/Copenhagen', 92, 0, 1),
    ('FI', 'FIN', '246', 'Finland', 'Suomi', 'Republic of Finland', '🇫🇮', '+358', 358, '+358 XX XXX XXXX', 9, 10, 'Europe', 'Northern Europe', 'Helsinki', 'EUR', '€', 'Europe/Helsinki', 93, 0, 1),
    ('IS', 'ISL', '352', 'Iceland', 'Ísland', 'Iceland', '🇮🇸', '+354', 354, '+354 XXX XXXX', 7, 7, 'Europe', 'Northern Europe', 'Reykjavik', 'ISK', 'kr', 'Atlantic/Reykjavik', 94, 0, 1),
    ('IE', 'IRL', '372', 'Ireland', 'Éire', 'Republic of Ireland', '🇮🇪', '+353', 353, '+353 XX XXX XXXX', 9, 9, 'Europe', 'Northern Europe', 'Dublin', 'EUR', '€', 'Europe/Dublin', 95, 0, 1),
    ('EE', 'EST', '233', 'Estonia', 'Eesti', 'Republic of Estonia', '🇪🇪', '+372', 372, '+372 XXXX XXXX', 8, 8, 'Europe', 'Northern Europe', 'Tallinn', 'EUR', '€', 'Europe/Tallinn', 96, 0, 1),
    ('LV', 'LVA', '428', 'Latvia', 'Latvija', 'Republic of Latvia', '🇱🇻', '+371', 371, '+371 XXXX XXXX', 8, 8, 'Europe', 'Northern Europe', 'Riga', 'EUR', '€', 'Europe/Riga', 97, 0, 1),
    ('LT', 'LTU', '440', 'Lithuania', 'Lietuva', 'Republic of Lithuania', '🇱🇹', '+370', 370, '+370 XXX XXXXX', 8, 8, 'Europe', 'Northern Europe', 'Vilnius', 'EUR', '€', 'Europe/Vilnius', 98, 0, 1),
    
    # ============== EUROPE - EASTERN ==============
    ('RU', 'RUS', '643', 'Russia', 'Россия', 'Russian Federation', '🇷🇺', '+7', 7, '+7 XXX XXX XX XX', 10, 10, 'Europe', 'Eastern Europe', 'Moscow', 'RUB', '₽', 'Europe/Moscow', 100, 0, 1),
    ('UA', 'UKR', '804', 'Ukraine', 'Україна', 'Ukraine', '🇺🇦', '+380', 380, '+380 XX XXX XXXX', 9, 9, 'Europe', 'Eastern Europe', 'Kyiv', 'UAH', '₴', 'Europe/Kiev', 101, 0, 1),
    ('BY', 'BLR', '112', 'Belarus', 'Беларусь', 'Republic of Belarus', '🇧🇾', '+375', 375, '+375 XX XXX XX XX', 9, 9, 'Europe', 'Eastern Europe', 'Minsk', 'BYN', 'Br', 'Europe/Minsk', 102, 0, 1),
    ('PL', 'POL', '616', 'Poland', 'Polska', 'Republic of Poland', '🇵🇱', '+48', 48, '+48 XXX XXX XXX', 9, 9, 'Europe', 'Eastern Europe', 'Warsaw', 'PLN', 'zł', 'Europe/Warsaw', 103, 0, 1),
    ('CZ', 'CZE', '203', 'Czech Republic', 'Česko', 'Czech Republic', '🇨🇿', '+420', 420, '+420 XXX XXX XXX', 9, 9, 'Europe', 'Eastern Europe', 'Prague', 'CZK', 'Kč', 'Europe/Prague', 104, 0, 1),
    ('SK', 'SVK', '703', 'Slovakia', 'Slovensko', 'Slovak Republic', '🇸🇰', '+421', 421, '+421 XXX XXX XXX', 9, 9, 'Europe', 'Eastern Europe', 'Bratislava', 'EUR', '€', 'Europe/Bratislava', 105, 0, 1),
    ('HU', 'HUN', '348', 'Hungary', 'Magyarország', 'Hungary', '🇭🇺', '+36', 36, '+36 XX XXX XXXX', 9, 9, 'Europe', 'Eastern Europe', 'Budapest', 'HUF', 'Ft', 'Europe/Budapest', 106, 0, 1),
    ('RO', 'ROU', '642', 'Romania', 'România', 'Romania', '🇷🇴', '+40', 40, '+40 XXX XXX XXX', 9, 9, 'Europe', 'Eastern Europe', 'Bucharest', 'RON', 'lei', 'Europe/Bucharest', 107, 0, 1),
    ('BG', 'BGR', '100', 'Bulgaria', 'България', 'Republic of Bulgaria', '🇧🇬', '+359', 359, '+359 XX XXX XXXX', 9, 9, 'Europe', 'Eastern Europe', 'Sofia', 'BGN', 'лв', 'Europe/Sofia', 108, 0, 1),
    ('MD', 'MDA', '498', 'Moldova', 'Moldova', 'Republic of Moldova', '🇲🇩', '+373', 373, '+373 XXXX XXXX', 8, 8, 'Europe', 'Eastern Europe', 'Chisinau', 'MDL', 'L', 'Europe/Chisinau', 109, 0, 1),
    
    # ============== EUROPE - BALKANS ==============
    ('GR', 'GRC', '300', 'Greece', 'Ελλάδα', 'Hellenic Republic', '🇬🇷', '+30', 30, '+30 XXX XXX XXXX', 10, 10, 'Europe', 'Southern Europe', 'Athens', 'EUR', '€', 'Europe/Athens', 110, 0, 1),
    ('AL', 'ALB', '008', 'Albania', 'Shqipëria', 'Republic of Albania', '🇦🇱', '+355', 355, '+355 XX XXX XXXX', 9, 9, 'Europe', 'Southern Europe', 'Tirana', 'ALL', 'L', 'Europe/Tirane', 111, 0, 1),
    ('MK', 'MKD', '807', 'North Macedonia', 'Северна Македонија', 'Republic of North Macedonia', '🇲🇰', '+389', 389, '+389 XX XXX XXX', 8, 8, 'Europe', 'Southern Europe', 'Skopje', 'MKD', 'ден', 'Europe/Skopje', 112, 0, 1),
    ('RS', 'SRB', '688', 'Serbia', 'Србија', 'Republic of Serbia', '🇷🇸', '+381', 381, '+381 XX XXX XXXX', 9, 9, 'Europe', 'Southern Europe', 'Belgrade', 'RSD', 'дин', 'Europe/Belgrade', 113, 0, 1),
    ('ME', 'MNE', '499', 'Montenegro', 'Crna Gora', 'Montenegro', '🇲🇪', '+382', 382, '+382 XX XXX XXX', 8, 8, 'Europe', 'Southern Europe', 'Podgorica', 'EUR', '€', 'Europe/Podgorica', 114, 0, 1),
    ('BA', 'BIH', '070', 'Bosnia and Herzegovina', 'Bosna i Hercegovina', 'Bosnia and Herzegovina', '🇧🇦', '+387', 387, '+387 XX XXX XXX', 8, 8, 'Europe', 'Southern Europe', 'Sarajevo', 'BAM', 'KM', 'Europe/Sarajevo', 115, 0, 1),
    ('HR', 'HRV', '191', 'Croatia', 'Hrvatska', 'Republic of Croatia', '🇭🇷', '+385', 385, '+385 XX XXX XXXX', 9, 9, 'Europe', 'Southern Europe', 'Zagreb', 'EUR', '€', 'Europe/Zagreb', 116, 0, 1),
    ('SI', 'SVN', '705', 'Slovenia', 'Slovenija', 'Republic of Slovenia', '🇸🇮', '+386', 386, '+386 XX XXX XXX', 8, 8, 'Europe', 'Southern Europe', 'Ljubljana', 'EUR', '€', 'Europe/Ljubljana', 117, 0, 1),
    ('XK', 'XKX', '383', 'Kosovo', 'Kosova', 'Republic of Kosovo', '🇽🇰', '+383', 383, '+383 XX XXX XXX', 8, 8, 'Europe', 'Southern Europe', 'Pristina', 'EUR', '€', 'Europe/Belgrade', 118, 0, 1),
    
    # ============== NORTH AMERICA ==============
    ('US', 'USA', '840', 'United States', 'United States', 'United States of America', '🇺🇸', '+1', 1, '+1 (XXX) XXX-XXXX', 10, 10, 'North America', 'Northern America', 'Washington, D.C.', 'USD', '$', 'America/New_York', 120, 0, 1),
    ('CA', 'CAN', '124', 'Canada', 'Canada', 'Canada', '🇨🇦', '+1', 1, '+1 (XXX) XXX-XXXX', 10, 10, 'North America', 'Northern America', 'Ottawa', 'CAD', '$', 'America/Toronto', 121, 0, 1),
    ('MX', 'MEX', '484', 'Mexico', 'México', 'United Mexican States', '🇲🇽', '+52', 52, '+52 XX XXXX XXXX', 10, 10, 'North America', 'Central America', 'Mexico City', 'MXN', '$', 'America/Mexico_City', 122, 0, 1),
    
    # ============== CENTRAL AMERICA ==============
    ('GT', 'GTM', '320', 'Guatemala', 'Guatemala', 'Republic of Guatemala', '🇬🇹', '+502', 502, '+502 XXXX XXXX', 8, 8, 'North America', 'Central America', 'Guatemala City', 'GTQ', 'Q', 'America/Guatemala', 125, 0, 1),
    ('BZ', 'BLZ', '084', 'Belize', 'Belize', 'Belize', '🇧🇿', '+501', 501, '+501 XXX XXXX', 7, 7, 'North America', 'Central America', 'Belmopan', 'BZD', '$', 'America/Belize', 126, 0, 1),
    ('SV', 'SLV', '222', 'El Salvador', 'El Salvador', 'Republic of El Salvador', '🇸🇻', '+503', 503, '+503 XXXX XXXX', 8, 8, 'North America', 'Central America', 'San Salvador', 'USD', '$', 'America/El_Salvador', 127, 0, 1),
    ('HN', 'HND', '340', 'Honduras', 'Honduras', 'Republic of Honduras', '🇭🇳', '+504', 504, '+504 XXXX XXXX', 8, 8, 'North America', 'Central America', 'Tegucigalpa', 'HNL', 'L', 'America/Tegucigalpa', 128, 0, 1),
    ('NI', 'NIC', '558', 'Nicaragua', 'Nicaragua', 'Republic of Nicaragua', '🇳🇮', '+505', 505, '+505 XXXX XXXX', 8, 8, 'North America', 'Central America', 'Managua', 'NIO', 'C$', 'America/Managua', 129, 0, 1),
    ('CR', 'CRI', '188', 'Costa Rica', 'Costa Rica', 'Republic of Costa Rica', '🇨🇷', '+506', 506, '+506 XXXX XXXX', 8, 8, 'North America', 'Central America', 'San José', 'CRC', '₡', 'America/Costa_Rica', 130, 0, 1),
    ('PA', 'PAN', '591', 'Panama', 'Panamá', 'Republic of Panama', '🇵🇦', '+507', 507, '+507 XXXX XXXX', 8, 8, 'North America', 'Central America', 'Panama City', 'PAB', 'B/.', 'America/Panama', 131, 0, 1),
    
    # ============== CARIBBEAN ==============
    ('CU', 'CUB', '192', 'Cuba', 'Cuba', 'Republic of Cuba', '🇨🇺', '+53', 53, '+53 X XXX XXXX', 8, 8, 'North America', 'Caribbean', 'Havana', 'CUP', '$', 'America/Havana', 135, 0, 1),
    ('JM', 'JAM', '388', 'Jamaica', 'Jamaica', 'Jamaica', '🇯🇲', '+1', 1, '+1 (876) XXX-XXXX', 10, 10, 'North America', 'Caribbean', 'Kingston', 'JMD', '$', 'America/Jamaica', 136, 0, 1),
    ('HT', 'HTI', '332', 'Haiti', 'Haïti', 'Republic of Haiti', '🇭🇹', '+509', 509, '+509 XXXX XXXX', 8, 8, 'North America', 'Caribbean', 'Port-au-Prince', 'HTG', 'G', 'America/Port-au-Prince', 137, 0, 1),
    ('DO', 'DOM', '214', 'Dominican Republic', 'República Dominicana', 'Dominican Republic', '🇩🇴', '+1', 1, '+1 (809) XXX-XXXX', 10, 10, 'North America', 'Caribbean', 'Santo Domingo', 'DOP', '$', 'America/Santo_Domingo', 138, 0, 1),
    ('PR', 'PRI', '630', 'Puerto Rico', 'Puerto Rico', 'Commonwealth of Puerto Rico', '🇵🇷', '+1', 1, '+1 (787) XXX-XXXX', 10, 10, 'North America', 'Caribbean', 'San Juan', 'USD', '$', 'America/Puerto_Rico', 139, 0, 1),
    ('BS', 'BHS', '044', 'Bahamas', 'Bahamas', 'Commonwealth of The Bahamas', '🇧🇸', '+1', 1, '+1 (242) XXX-XXXX', 10, 10, 'North America', 'Caribbean', 'Nassau', 'BSD', '$', 'America/Nassau', 140, 0, 1),
    ('BB', 'BRB', '052', 'Barbados', 'Barbados', 'Barbados', '🇧🇧', '+1', 1, '+1 (246) XXX-XXXX', 10, 10, 'North America', 'Caribbean', 'Bridgetown', 'BBD', '$', 'America/Barbados', 141, 0, 1),
    ('TT', 'TTO', '780', 'Trinidad and Tobago', 'Trinidad and Tobago', 'Republic of Trinidad and Tobago', '🇹🇹', '+1', 1, '+1 (868) XXX-XXXX', 10, 10, 'North America', 'Caribbean', 'Port of Spain', 'TTD', '$', 'America/Port_of_Spain', 142, 0, 1),
    ('AG', 'ATG', '028', 'Antigua and Barbuda', 'Antigua and Barbuda', 'Antigua and Barbuda', '🇦🇬', '+1', 1, '+1 (268) XXX-XXXX', 10, 10, 'North America', 'Caribbean', "Saint John's", 'XCD', '$', 'America/Antigua', 143, 0, 1),
    ('DM', 'DMA', '212', 'Dominica', 'Dominica', 'Commonwealth of Dominica', '🇩🇲', '+1', 1, '+1 (767) XXX-XXXX', 10, 10, 'North America', 'Caribbean', 'Roseau', 'XCD', '$', 'America/Dominica', 144, 0, 1),
    ('GD', 'GRD', '308', 'Grenada', 'Grenada', 'Grenada', '🇬🇩', '+1', 1, '+1 (473) XXX-XXXX', 10, 10, 'North America', 'Caribbean', "St. George's", 'XCD', '$', 'America/Grenada', 145, 0, 1),
    ('KN', 'KNA', '659', 'Saint Kitts and Nevis', 'Saint Kitts and Nevis', 'Federation of Saint Christopher and Nevis', '🇰🇳', '+1', 1, '+1 (869) XXX-XXXX', 10, 10, 'North America', 'Caribbean', 'Basseterre', 'XCD', '$', 'America/St_Kitts', 146, 0, 1),
    ('LC', 'LCA', '662', 'Saint Lucia', 'Saint Lucia', 'Saint Lucia', '🇱🇨', '+1', 1, '+1 (758) XXX-XXXX', 10, 10, 'North America', 'Caribbean', 'Castries', 'XCD', '$', 'America/St_Lucia', 147, 0, 1),
    ('VC', 'VCT', '670', 'Saint Vincent and the Grenadines', 'Saint Vincent and the Grenadines', 'Saint Vincent and the Grenadines', '🇻🇨', '+1', 1, '+1 (784) XXX-XXXX', 10, 10, 'North America', 'Caribbean', 'Kingstown', 'XCD', '$', 'America/St_Vincent', 148, 0, 1),
    
    # ============== SOUTH AMERICA ==============
    ('BR', 'BRA', '076', 'Brazil', 'Brasil', 'Federative Republic of Brazil', '🇧🇷', '+55', 55, '+55 XX XXXXX XXXX', 10, 11, 'South America', 'South America', 'Brasília', 'BRL', 'R$', 'America/Sao_Paulo', 150, 0, 1),
    ('AR', 'ARG', '032', 'Argentina', 'Argentina', 'Argentine Republic', '🇦🇷', '+54', 54, '+54 XX XXXX XXXX', 10, 10, 'South America', 'South America', 'Buenos Aires', 'ARS', '$', 'America/Argentina/Buenos_Aires', 151, 0, 1),
    ('CL', 'CHL', '152', 'Chile', 'Chile', 'Republic of Chile', '🇨🇱', '+56', 56, '+56 X XXXX XXXX', 9, 9, 'South America', 'South America', 'Santiago', 'CLP', '$', 'America/Santiago', 152, 0, 1),
    ('CO', 'COL', '170', 'Colombia', 'Colombia', 'Republic of Colombia', '🇨🇴', '+57', 57, '+57 XXX XXX XXXX', 10, 10, 'South America', 'South America', 'Bogotá', 'COP', '$', 'America/Bogota', 153, 0, 1),
    ('PE', 'PER', '604', 'Peru', 'Perú', 'Republic of Peru', '🇵🇪', '+51', 51, '+51 XXX XXX XXX', 9, 9, 'South America', 'South America', 'Lima', 'PEN', 'S/', 'America/Lima', 154, 0, 1),
    ('VE', 'VEN', '862', 'Venezuela', 'Venezuela', 'Bolivarian Republic of Venezuela', '🇻🇪', '+58', 58, '+58 XXX XXX XXXX', 10, 10, 'South America', 'South America', 'Caracas', 'VES', 'Bs', 'America/Caracas', 155, 0, 1),
    ('EC', 'ECU', '218', 'Ecuador', 'Ecuador', 'Republic of Ecuador', '🇪🇨', '+593', 593, '+593 XX XXX XXXX', 9, 9, 'South America', 'South America', 'Quito', 'USD', '$', 'America/Guayaquil', 156, 0, 1),
    ('BO', 'BOL', '068', 'Bolivia', 'Bolivia', 'Plurinational State of Bolivia', '🇧🇴', '+591', 591, '+591 X XXX XXXX', 8, 8, 'South America', 'South America', 'Sucre', 'BOB', 'Bs.', 'America/La_Paz', 157, 0, 1),
    ('PY', 'PRY', '600', 'Paraguay', 'Paraguay', 'Republic of Paraguay', '🇵🇾', '+595', 595, '+595 XXX XXX XXX', 9, 9, 'South America', 'South America', 'Asunción', 'PYG', '₲', 'America/Asuncion', 158, 0, 1),
    ('UY', 'URY', '858', 'Uruguay', 'Uruguay', 'Oriental Republic of Uruguay', '🇺🇾', '+598', 598, '+598 X XXX XXXX', 8, 8, 'South America', 'South America', 'Montevideo', 'UYU', '$', 'America/Montevideo', 159, 0, 1),
    ('GY', 'GUY', '328', 'Guyana', 'Guyana', 'Co-operative Republic of Guyana', '🇬🇾', '+592', 592, '+592 XXX XXXX', 7, 7, 'South America', 'South America', 'Georgetown', 'GYD', '$', 'America/Guyana', 160, 0, 1),
    ('SR', 'SUR', '740', 'Suriname', 'Suriname', 'Republic of Suriname', '🇸🇷', '+597', 597, '+597 XXX XXXX', 7, 7, 'South America', 'South America', 'Paramaribo', 'SRD', '$', 'America/Paramaribo', 161, 0, 1),
    
    # ============== AFRICA - NORTH ==============
    ('EG', 'EGY', '818', 'Egypt', 'مصر', 'Arab Republic of Egypt', '🇪🇬', '+20', 20, '+20 XX XXXX XXXX', 10, 10, 'Africa', 'Northern Africa', 'Cairo', 'EGP', '£', 'Africa/Cairo', 165, 0, 1),
    ('LY', 'LBY', '434', 'Libya', 'ليبيا', 'State of Libya', '🇱🇾', '+218', 218, '+218 XX XXX XXXX', 9, 9, 'Africa', 'Northern Africa', 'Tripoli', 'LYD', 'ل.د', 'Africa/Tripoli', 166, 0, 1),
    ('TN', 'TUN', '788', 'Tunisia', 'تونس', 'Republic of Tunisia', '🇹🇳', '+216', 216, '+216 XX XXX XXX', 8, 8, 'Africa', 'Northern Africa', 'Tunis', 'TND', 'د.ت', 'Africa/Tunis', 167, 0, 1),
    ('DZ', 'DZA', '012', 'Algeria', 'الجزائر', "People's Democratic Republic of Algeria", '🇩🇿', '+213', 213, '+213 XXX XX XX XX', 9, 9, 'Africa', 'Northern Africa', 'Algiers', 'DZD', 'د.ج', 'Africa/Algiers', 168, 0, 1),
    ('MA', 'MAR', '504', 'Morocco', 'المغرب', 'Kingdom of Morocco', '🇲🇦', '+212', 212, '+212 XXX XXXXXX', 9, 9, 'Africa', 'Northern Africa', 'Rabat', 'MAD', 'د.م.', 'Africa/Casablanca', 169, 0, 1),
    ('SD', 'SDN', '729', 'Sudan', 'السودان', 'Republic of the Sudan', '🇸🇩', '+249', 249, '+249 XX XXX XXXX', 9, 9, 'Africa', 'Northern Africa', 'Khartoum', 'SDG', 'ج.س', 'Africa/Khartoum', 170, 0, 1),
    ('SS', 'SSD', '728', 'South Sudan', 'South Sudan', 'Republic of South Sudan', '🇸🇸', '+211', 211, '+211 XX XXX XXXX', 9, 9, 'Africa', 'Eastern Africa', 'Juba', 'SSP', '£', 'Africa/Juba', 171, 0, 1),
    
    # ============== AFRICA - WEST ==============
    ('NG', 'NGA', '566', 'Nigeria', 'Nigeria', 'Federal Republic of Nigeria', '🇳🇬', '+234', 234, '+234 XXX XXX XXXX', 10, 10, 'Africa', 'Western Africa', 'Abuja', 'NGN', '₦', 'Africa/Lagos', 175, 0, 1),
    ('GH', 'GHA', '288', 'Ghana', 'Ghana', 'Republic of Ghana', '🇬🇭', '+233', 233, '+233 XX XXX XXXX', 9, 9, 'Africa', 'Western Africa', 'Accra', 'GHS', '₵', 'Africa/Accra', 176, 0, 1),
    ('CI', 'CIV', '384', "Côte d'Ivoire", "Côte d'Ivoire", "Republic of Côte d'Ivoire", '🇨🇮', '+225', 225, '+225 XX XX XX XXXX', 10, 10, 'Africa', 'Western Africa', 'Yamoussoukro', 'XOF', 'CFA', 'Africa/Abidjan', 177, 0, 1),
    ('SN', 'SEN', '686', 'Senegal', 'Sénégal', 'Republic of Senegal', '🇸🇳', '+221', 221, '+221 XX XXX XXXX', 9, 9, 'Africa', 'Western Africa', 'Dakar', 'XOF', 'CFA', 'Africa/Dakar', 178, 0, 1),
    ('ML', 'MLI', '466', 'Mali', 'Mali', 'Republic of Mali', '🇲🇱', '+223', 223, '+223 XXXX XXXX', 8, 8, 'Africa', 'Western Africa', 'Bamako', 'XOF', 'CFA', 'Africa/Bamako', 179, 0, 1),
    ('BF', 'BFA', '854', 'Burkina Faso', 'Burkina Faso', 'Burkina Faso', '🇧🇫', '+226', 226, '+226 XX XX XXXX', 8, 8, 'Africa', 'Western Africa', 'Ouagadougou', 'XOF', 'CFA', 'Africa/Ouagadougou', 180, 0, 1),
    ('NE', 'NER', '562', 'Niger', 'Niger', 'Republic of Niger', '🇳🇪', '+227', 227, '+227 XX XX XXXX', 8, 8, 'Africa', 'Western Africa', 'Niamey', 'XOF', 'CFA', 'Africa/Niamey', 181, 0, 1),
    ('MR', 'MRT', '478', 'Mauritania', 'موريتانيا', 'Islamic Republic of Mauritania', '🇲🇷', '+222', 222, '+222 XXXX XXXX', 8, 8, 'Africa', 'Western Africa', 'Nouakchott', 'MRU', 'UM', 'Africa/Nouakchott', 182, 0, 1),
    ('GM', 'GMB', '270', 'Gambia', 'Gambia', 'Republic of The Gambia', '🇬🇲', '+220', 220, '+220 XXX XXXX', 7, 7, 'Africa', 'Western Africa', 'Banjul', 'GMD', 'D', 'Africa/Banjul', 183, 0, 1),
    ('GW', 'GNB', '624', 'Guinea-Bissau', 'Guiné-Bissau', 'Republic of Guinea-Bissau', '🇬🇼', '+245', 245, '+245 XXX XXXX', 7, 7, 'Africa', 'Western Africa', 'Bissau', 'XOF', 'CFA', 'Africa/Bissau', 184, 0, 1),
    ('GN', 'GIN', '324', 'Guinea', 'Guinée', 'Republic of Guinea', '🇬🇳', '+224', 224, '+224 XXX XX XX XX', 9, 9, 'Africa', 'Western Africa', 'Conakry', 'GNF', 'FG', 'Africa/Conakry', 185, 0, 1),
    ('SL', 'SLE', '694', 'Sierra Leone', 'Sierra Leone', 'Republic of Sierra Leone', '🇸🇱', '+232', 232, '+232 XX XXXXXX', 8, 8, 'Africa', 'Western Africa', 'Freetown', 'SLE', 'Le', 'Africa/Freetown', 186, 0, 1),
    ('LR', 'LBR', '430', 'Liberia', 'Liberia', 'Republic of Liberia', '🇱🇷', '+231', 231, '+231 XX XXX XXXX', 9, 9, 'Africa', 'Western Africa', 'Monrovia', 'LRD', '$', 'Africa/Monrovia', 187, 0, 1),
    ('CV', 'CPV', '132', 'Cabo Verde', 'Cabo Verde', 'Republic of Cabo Verde', '🇨🇻', '+238', 238, '+238 XXX XXXX', 7, 7, 'Africa', 'Western Africa', 'Praia', 'CVE', '$', 'Atlantic/Cape_Verde', 188, 0, 1),
    ('TG', 'TGO', '768', 'Togo', 'Togo', 'Togolese Republic', '🇹🇬', '+228', 228, '+228 XX XXX XXX', 8, 8, 'Africa', 'Western Africa', 'Lomé', 'XOF', 'CFA', 'Africa/Lome', 189, 0, 1),
    ('BJ', 'BEN', '204', 'Benin', 'Bénin', 'Republic of Benin', '🇧🇯', '+229', 229, '+229 XX XXX XXX', 8, 8, 'Africa', 'Western Africa', 'Porto-Novo', 'XOF', 'CFA', 'Africa/Porto-Novo', 190, 0, 1),
    
    # ============== AFRICA - EAST ==============
    ('KE', 'KEN', '404', 'Kenya', 'Kenya', 'Republic of Kenya', '🇰🇪', '+254', 254, '+254 XXX XXXXXX', 9, 9, 'Africa', 'Eastern Africa', 'Nairobi', 'KES', 'KSh', 'Africa/Nairobi', 195, 0, 1),
    ('ET', 'ETH', '231', 'Ethiopia', 'ኢትዮጵያ', 'Federal Democratic Republic of Ethiopia', '🇪🇹', '+251', 251, '+251 XX XXX XXXX', 9, 9, 'Africa', 'Eastern Africa', 'Addis Ababa', 'ETB', 'Br', 'Africa/Addis_Ababa', 196, 0, 1),
    ('TZ', 'TZA', '834', 'Tanzania', 'Tanzania', 'United Republic of Tanzania', '🇹🇿', '+255', 255, '+255 XXX XXX XXX', 9, 9, 'Africa', 'Eastern Africa', 'Dodoma', 'TZS', 'TSh', 'Africa/Dar_es_Salaam', 197, 0, 1),
    ('UG', 'UGA', '800', 'Uganda', 'Uganda', 'Republic of Uganda', '🇺🇬', '+256', 256, '+256 XXX XXXXXX', 9, 9, 'Africa', 'Eastern Africa', 'Kampala', 'UGX', 'USh', 'Africa/Kampala', 198, 0, 1),
    ('RW', 'RWA', '646', 'Rwanda', 'Rwanda', 'Republic of Rwanda', '🇷🇼', '+250', 250, '+250 XXX XXX XXX', 9, 9, 'Africa', 'Eastern Africa', 'Kigali', 'RWF', 'FRw', 'Africa/Kigali', 199, 0, 1),
    ('BI', 'BDI', '108', 'Burundi', 'Burundi', 'Republic of Burundi', '🇧🇮', '+257', 257, '+257 XX XX XXXX', 8, 8, 'Africa', 'Eastern Africa', 'Gitega', 'BIF', 'FBu', 'Africa/Bujumbura', 200, 0, 1),
    ('SO', 'SOM', '706', 'Somalia', 'Soomaaliya', 'Federal Republic of Somalia', '🇸🇴', '+252', 252, '+252 XX XXX XXX', 8, 8, 'Africa', 'Eastern Africa', 'Mogadishu', 'SOS', 'Sh', 'Africa/Mogadishu', 201, 0, 1),
    ('DJ', 'DJI', '262', 'Djibouti', 'Djibouti', 'Republic of Djibouti', '🇩🇯', '+253', 253, '+253 XX XX XX XX', 8, 8, 'Africa', 'Eastern Africa', 'Djibouti', 'DJF', 'Fdj', 'Africa/Djibouti', 202, 0, 1),
    ('ER', 'ERI', '232', 'Eritrea', 'ኤርትራ', 'State of Eritrea', '🇪🇷', '+291', 291, '+291 X XXX XXX', 7, 7, 'Africa', 'Eastern Africa', 'Asmara', 'ERN', 'Nfk', 'Africa/Asmara', 203, 0, 1),
    ('MG', 'MDG', '450', 'Madagascar', 'Madagasikara', 'Republic of Madagascar', '🇲🇬', '+261', 261, '+261 XX XX XXX XX', 9, 9, 'Africa', 'Eastern Africa', 'Antananarivo', 'MGA', 'Ar', 'Indian/Antananarivo', 204, 0, 1),
    ('MU', 'MUS', '480', 'Mauritius', 'Maurice', 'Republic of Mauritius', '🇲🇺', '+230', 230, '+230 XXXX XXXX', 8, 8, 'Africa', 'Eastern Africa', 'Port Louis', 'MUR', '₨', 'Indian/Mauritius', 205, 0, 1),
    ('SC', 'SYC', '690', 'Seychelles', 'Seychelles', 'Republic of Seychelles', '🇸🇨', '+248', 248, '+248 X XX XX XX', 7, 7, 'Africa', 'Eastern Africa', 'Victoria', 'SCR', '₨', 'Indian/Mahe', 206, 0, 1),
    ('KM', 'COM', '174', 'Comoros', 'Komori', 'Union of the Comoros', '🇰🇲', '+269', 269, '+269 XXX XXXX', 7, 7, 'Africa', 'Eastern Africa', 'Moroni', 'KMF', 'CF', 'Indian/Comoro', 207, 0, 1),
    
    # ============== AFRICA - CENTRAL ==============
    ('CD', 'COD', '180', 'Democratic Republic of the Congo', 'République démocratique du Congo', 'Democratic Republic of the Congo', '🇨🇩', '+243', 243, '+243 XXX XXX XXX', 9, 9, 'Africa', 'Central Africa', 'Kinshasa', 'CDF', 'FC', 'Africa/Kinshasa', 210, 0, 1),
    ('CG', 'COG', '178', 'Republic of the Congo', 'République du Congo', 'Republic of the Congo', '🇨🇬', '+242', 242, '+242 XX XXX XXXX', 9, 9, 'Africa', 'Central Africa', 'Brazzaville', 'XAF', 'FCFA', 'Africa/Brazzaville', 211, 0, 1),
    ('CM', 'CMR', '120', 'Cameroon', 'Cameroun', 'Republic of Cameroon', '🇨🇲', '+237', 237, '+237 XXXX XXXX', 8, 8, 'Africa', 'Central Africa', 'Yaoundé', 'XAF', 'FCFA', 'Africa/Douala', 212, 0, 1),
    ('CF', 'CAF', '140', 'Central African Republic', 'République centrafricaine', 'Central African Republic', '🇨🇫', '+236', 236, '+236 XX XX XX XX', 8, 8, 'Africa', 'Central Africa', 'Bangui', 'XAF', 'FCFA', 'Africa/Bangui', 213, 0, 1),
    ('TD', 'TCD', '148', 'Chad', 'Tchad', 'Republic of Chad', '🇹🇩', '+235', 235, '+235 XX XX XX XX', 8, 8, 'Africa', 'Central Africa', "N'Djamena", 'XAF', 'FCFA', 'Africa/Ndjamena', 214, 0, 1),
    ('GA', 'GAB', '266', 'Gabon', 'Gabon', 'Gabonese Republic', '🇬🇦', '+241', 241, '+241 X XX XX XX', 7, 7, 'Africa', 'Central Africa', 'Libreville', 'XAF', 'FCFA', 'Africa/Libreville', 215, 0, 1),
    ('GQ', 'GNQ', '226', 'Equatorial Guinea', 'Guinea Ecuatorial', 'Republic of Equatorial Guinea', '🇬🇶', '+240', 240, '+240 XXX XXX XXX', 9, 9, 'Africa', 'Central Africa', 'Malabo', 'XAF', 'FCFA', 'Africa/Malabo', 216, 0, 1),
    ('ST', 'STP', '678', 'São Tomé and Príncipe', 'São Tomé e Príncipe', 'Democratic Republic of São Tomé and Príncipe', '🇸🇹', '+239', 239, '+239 XXX XXXX', 7, 7, 'Africa', 'Central Africa', 'São Tomé', 'STN', 'Db', 'Africa/Sao_Tome', 217, 0, 1),
    ('AO', 'AGO', '024', 'Angola', 'Angola', 'Republic of Angola', '🇦🇴', '+244', 244, '+244 XXX XXX XXX', 9, 9, 'Africa', 'Central Africa', 'Luanda', 'AOA', 'Kz', 'Africa/Luanda', 218, 0, 1),
    
    # ============== AFRICA - SOUTH ==============
    ('ZA', 'ZAF', '710', 'South Africa', 'South Africa', 'Republic of South Africa', '🇿🇦', '+27', 27, '+27 XX XXX XXXX', 9, 9, 'Africa', 'Southern Africa', 'Pretoria', 'ZAR', 'R', 'Africa/Johannesburg', 220, 0, 1),
    ('NA', 'NAM', '516', 'Namibia', 'Namibia', 'Republic of Namibia', '🇳🇦', '+264', 264, '+264 XX XXX XXXX', 9, 9, 'Africa', 'Southern Africa', 'Windhoek', 'NAD', '$', 'Africa/Windhoek', 221, 0, 1),
    ('BW', 'BWA', '072', 'Botswana', 'Botswana', 'Republic of Botswana', '🇧🇼', '+267', 267, '+267 XX XXX XXX', 8, 8, 'Africa', 'Southern Africa', 'Gaborone', 'BWP', 'P', 'Africa/Gaborone', 222, 0, 1),
    ('ZW', 'ZWE', '716', 'Zimbabwe', 'Zimbabwe', 'Republic of Zimbabwe', '🇿🇼', '+263', 263, '+263 XX XXX XXXX', 9, 9, 'Africa', 'Southern Africa', 'Harare', 'ZWL', '$', 'Africa/Harare', 223, 0, 1),
    ('ZM', 'ZMB', '894', 'Zambia', 'Zambia', 'Republic of Zambia', '🇿🇲', '+260', 260, '+260 XX XXX XXXX', 9, 9, 'Africa', 'Southern Africa', 'Lusaka', 'ZMW', 'ZK', 'Africa/Lusaka', 224, 0, 1),
    ('MW', 'MWI', '454', 'Malawi', 'Malawi', 'Republic of Malawi', '🇲🇼', '+265', 265, '+265 X XXXX XXXX', 9, 9, 'Africa', 'Southern Africa', 'Lilongwe', 'MWK', 'MK', 'Africa/Blantyre', 225, 0, 1),
    ('MZ', 'MOZ', '508', 'Mozambique', 'Moçambique', 'Republic of Mozambique', '🇲🇿', '+258', 258, '+258 XX XXX XXXX', 9, 9, 'Africa', 'Southern Africa', 'Maputo', 'MZN', 'MT', 'Africa/Maputo', 226, 0, 1),
    ('SZ', 'SWZ', '748', 'Eswatini', 'Eswatini', 'Kingdom of Eswatini', '🇸🇿', '+268', 268, '+268 XXXX XXXX', 8, 8, 'Africa', 'Southern Africa', 'Mbabane', 'SZL', 'L', 'Africa/Mbabane', 227, 0, 1),
    ('LS', 'LSO', '426', 'Lesotho', 'Lesotho', 'Kingdom of Lesotho', '🇱🇸', '+266', 266, '+266 XXXX XXXX', 8, 8, 'Africa', 'Southern Africa', 'Maseru', 'LSL', 'L', 'Africa/Maseru', 228, 0, 1),
    
    # ============== OCEANIA ==============
    ('AU', 'AUS', '036', 'Australia', 'Australia', 'Commonwealth of Australia', '🇦🇺', '+61', 61, '+61 X XXXX XXXX', 9, 9, 'Oceania', 'Australia and New Zealand', 'Canberra', 'AUD', '$', 'Australia/Sydney', 230, 0, 1),
    ('NZ', 'NZL', '554', 'New Zealand', 'New Zealand', 'New Zealand', '🇳🇿', '+64', 64, '+64 XX XXX XXXX', 9, 9, 'Oceania', 'Australia and New Zealand', 'Wellington', 'NZD', '$', 'Pacific/Auckland', 231, 0, 1),
    ('PG', 'PNG', '598', 'Papua New Guinea', 'Papua New Guinea', 'Independent State of Papua New Guinea', '🇵🇬', '+675', 675, '+675 XXX XXXX', 7, 8, 'Oceania', 'Melanesia', 'Port Moresby', 'PGK', 'K', 'Pacific/Port_Moresby', 232, 0, 1),
    ('FJ', 'FJI', '242', 'Fiji', 'Fiji', 'Republic of Fiji', '🇫🇯', '+679', 679, '+679 XXX XXXX', 7, 7, 'Oceania', 'Melanesia', 'Suva', 'FJD', '$', 'Pacific/Fiji', 233, 0, 1),
    ('SB', 'SLB', '090', 'Solomon Islands', 'Solomon Islands', 'Solomon Islands', '🇸🇧', '+677', 677, '+677 XXXXX', 5, 7, 'Oceania', 'Melanesia', 'Honiara', 'SBD', '$', 'Pacific/Guadalcanal', 234, 0, 1),
    ('VU', 'VUT', '548', 'Vanuatu', 'Vanuatu', 'Republic of Vanuatu', '🇻🇺', '+678', 678, '+678 XXX XXXX', 7, 7, 'Oceania', 'Melanesia', 'Port Vila', 'VUV', 'Vt', 'Pacific/Efate', 235, 0, 1),
    ('NC', 'NCL', '540', 'New Caledonia', 'Nouvelle-Calédonie', 'New Caledonia', '🇳🇨', '+687', 687, '+687 XX XX XX', 6, 6, 'Oceania', 'Melanesia', 'Nouméa', 'XPF', '₣', 'Pacific/Noumea', 236, 0, 1),
    ('WS', 'WSM', '882', 'Samoa', 'Samoa', 'Independent State of Samoa', '🇼🇸', '+685', 685, '+685 XX XXXX', 7, 7, 'Oceania', 'Polynesia', 'Apia', 'WST', 'T', 'Pacific/Apia', 237, 0, 1),
    ('TO', 'TON', '776', 'Tonga', 'Tonga', 'Kingdom of Tonga', '🇹🇴', '+676', 676, '+676 XXX XXXX', 7, 7, 'Oceania', 'Polynesia', "Nuku'alofa", 'TOP', 'T$', 'Pacific/Tongatapu', 238, 0, 1),
    ('KI', 'KIR', '296', 'Kiribati', 'Kiribati', 'Republic of Kiribati', '🇰🇮', '+686', 686, '+686 XXXX XXXX', 8, 8, 'Oceania', 'Micronesia', 'Tarawa', 'AUD', '$', 'Pacific/Tarawa', 239, 0, 1),
    ('FM', 'FSM', '583', 'Micronesia', 'Micronesia', 'Federated States of Micronesia', '🇫🇲', '+691', 691, '+691 XXX XXXX', 7, 7, 'Oceania', 'Micronesia', 'Palikir', 'USD', '$', 'Pacific/Pohnpei', 240, 0, 1),
    ('MH', 'MHL', '584', 'Marshall Islands', 'Marshall Islands', 'Republic of the Marshall Islands', '🇲🇭', '+692', 692, '+692 XXX XXXX', 7, 7, 'Oceania', 'Micronesia', 'Majuro', 'USD', '$', 'Pacific/Majuro', 241, 0, 1),
    ('PW', 'PLW', '585', 'Palau', 'Palau', 'Republic of Palau', '🇵🇼', '+680', 680, '+680 XXX XXXX', 7, 7, 'Oceania', 'Micronesia', 'Ngerulmud', 'USD', '$', 'Pacific/Palau', 242, 0, 1),
    ('NR', 'NRU', '520', 'Nauru', 'Nauru', 'Republic of Nauru', '🇳🇷', '+674', 674, '+674 XXX XXXX', 7, 7, 'Oceania', 'Micronesia', 'Yaren', 'AUD', '$', 'Pacific/Nauru', 243, 0, 1),
    ('TV', 'TUV', '798', 'Tuvalu', 'Tuvalu', 'Tuvalu', '🇹🇻', '+688', 688, '+688 XXXXX', 5, 6, 'Oceania', 'Polynesia', 'Funafuti', 'AUD', '$', 'Pacific/Funafuti', 244, 0, 1),
]

def main():
    print("=" * 60)
    print("  Insert ALL Countries to Database")
    print("=" * 60)
    print()
    
    try:
        print(f"Connecting to {DB_CONFIG['database']}@{DB_CONFIG['host']}...")
        connection = pymysql.connect(**DB_CONFIG)
        cursor = connection.cursor()
        print("Connected successfully!")
        print()
        
        print(f"Inserting {len(COUNTRIES)} countries...")
        inserted = 0
        updated = 0
        errors = 0
        
        for country in COUNTRIES:
            try:
                cursor.execute(INSERT_SQL, country)
                if cursor.rowcount == 1:
                    inserted += 1
                else:
                    updated += 1
            except Exception as e:
                errors += 1
                print(f"  Error with {country[3]}: {e}")
        
        connection.commit()
        print()
        print(f"Results: Inserted={inserted}, Updated={updated}, Errors={errors}")
        
        # Show count by continent
        cursor.execute("""
            SELECT continent, COUNT(*) as cnt
            FROM countries 
            GROUP BY continent
            ORDER BY cnt DESC
        """)
        regions = cursor.fetchall()
        print()
        print("Countries by Continent:")
        print("-" * 40)
        total = 0
        for r in regions:
            print(f"  {r[0]}: {r[1]}")
            total += r[1]
        print("-" * 40)
        print(f"  TOTAL: {total} countries")
        
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    print()
    print("=" * 60)
    print("  Complete!")
    print("=" * 60)
    return 0


if __name__ == '__main__':
    exit(main())
