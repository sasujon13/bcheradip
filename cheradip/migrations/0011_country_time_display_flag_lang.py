# Add time_display (e.g. GMT+6), populate flag_url and language_codes for cheradip_country

from django.db import migrations, models


# IANA timezone -> display string (GMT+6 style). Same display for same offset.
TIMEZONE_TO_DISPLAY = {
    'Asia/Dhaka': 'GMT+6', 'Asia/Thimphu': 'GMT+6', 'Asia/Almaty': 'GMT+6', 'Asia/Bishkek': 'GMT+6',
    'Asia/Kolkata': 'GMT+5:30', 'Asia/Kathmandu': 'GMT+5:45',
    'Asia/Karachi': 'GMT+5', 'Asia/Tashkent': 'GMT+5', 'Asia/Yekaterinburg': 'GMT+5',
    'Asia/Dubai': 'GMT+4', 'Asia/Tbilisi': 'GMT+4', 'Asia/Baku': 'GMT+4', 'Asia/Yerevan': 'GMT+4',
    'Asia/Riyadh': 'GMT+3', 'Asia/Baghdad': 'GMT+3', 'Asia/Kuwait': 'GMT+3', 'Africa/Nairobi': 'GMT+3',
    'Europe/Moscow': 'GMT+3', 'Europe/Istanbul': 'GMT+3', 'Africa/Cairo': 'GMT+2',
    'Europe/Kiev': 'GMT+2', 'Europe/Athens': 'GMT+2', 'Europe/Berlin': 'GMT+1', 'Europe/Paris': 'GMT+1',
    'Europe/London': 'GMT+0', 'Atlantic/Reykjavik': 'GMT+0',
    'America/New_York': 'GMT-5', 'America/Chicago': 'GMT-6', 'America/Denver': 'GMT-7',
    'America/Los_Angeles': 'GMT-8', 'America/Anchorage': 'GMT-9', 'Pacific/Honolulu': 'GMT-10',
    'Asia/Shanghai': 'GMT+8', 'Asia/Hong_Kong': 'GMT+8', 'Asia/Singapore': 'GMT+8',
    'Asia/Bangkok': 'GMT+7', 'Asia/Jakarta': 'GMT+7', 'Asia/Ho_Chi_Minh': 'GMT+7',
    'Asia/Tokyo': 'GMT+9', 'Asia/Seoul': 'GMT+9', 'Australia/Sydney': 'GMT+10', 'Pacific/Auckland': 'GMT+12',
    'Asia/Colombo': 'GMT+5:30', 'Indian/Maldives': 'GMT+5', 'Asia/Kabul': 'GMT+4:30',
    'Asia/Tehran': 'GMT+3:30',
    'America/Toronto': 'GMT-5', 'America/Mexico_City': 'GMT-6', 'America/Sao_Paulo': 'GMT-3',
    'America/Argentina/Buenos_Aires': 'GMT-3', 'America/Lima': 'GMT-5', 'America/Bogota': 'GMT-5',
    'Africa/Lagos': 'GMT+1', 'Africa/Johannesburg': 'GMT+2', 'Africa/Casablanca': 'GMT+1',
    'Pacific/Fiji': 'GMT+12', 'Pacific/Port_Moresby': 'GMT+10', 'Pacific/Guadalcanal': 'GMT+11',
}
# Fallback for unknown timezone (keep IANA or generic)
DEFAULT_TIME_DISPLAY = 'GMT+0'

# Country code -> ISO 639-1 language codes. Same language = same code everywhere.
COUNTRY_LANGUAGES = {
    'BD': ['bn', 'en'], 'IN': ['hi', 'en'], 'PK': ['ur', 'en'], 'NP': ['ne', 'en'], 'LK': ['si', 'ta', 'en'],
    'BT': ['dz'], 'MV': ['dv'], 'AF': ['fa', 'ps'],
    'AE': ['ar', 'en'], 'SA': ['ar'], 'QA': ['ar'], 'KW': ['ar'], 'BH': ['ar'], 'OM': ['ar'], 'YE': ['ar'],
    'IR': ['fa'], 'IQ': ['ar', 'ku'], 'JO': ['ar'], 'LB': ['ar'], 'SY': ['ar'], 'PS': ['ar'], 'IL': ['he', 'ar'],
    'TR': ['tr'], 'CY': ['el', 'tr'],
    'MY': ['ms', 'en'], 'SG': ['en', 'zh', 'ms'], 'ID': ['id'], 'TH': ['th'], 'PH': ['tl', 'en'], 'VN': ['vi'],
    'MM': ['my'], 'KH': ['km'], 'LA': ['lo'], 'BN': ['ms'], 'TL': ['pt', 'tet'],
    'CN': ['zh'], 'JP': ['ja'], 'KR': ['ko'], 'KP': ['ko'], 'TW': ['zh'], 'HK': ['zh', 'en'], 'MO': ['zh', 'pt'], 'MN': ['mn'],
    'KZ': ['kk', 'ru'], 'UZ': ['uz'], 'TM': ['tk'], 'KG': ['ky', 'ru'], 'TJ': ['tg'],
    'GE': ['ka'], 'AM': ['hy'], 'AZ': ['az'],
    'GB': ['en'], 'DE': ['de'], 'FR': ['fr'], 'IT': ['it'], 'ES': ['es'], 'PT': ['pt'], 'NL': ['nl'], 'BE': ['nl', 'fr', 'de'],
    'CH': ['de', 'fr', 'it', 'en'], 'AT': ['de'], 'LU': ['fr', 'de', 'lb'], 'LI': ['de'], 'MC': ['fr'], 'AD': ['ca'],
    'SM': ['it'], 'VA': ['it', 'la'], 'MT': ['mt', 'en'], 'GR': ['el'], 'AL': ['sq'], 'MK': ['mk'], 'RS': ['sr'],
    'ME': ['sr', 'bs', 'sq', 'hr'], 'BA': ['bs', 'hr', 'sr'], 'HR': ['hr'], 'SI': ['sl'], 'XK': ['sq', 'sr'],
    'SE': ['sv'], 'NO': ['no'], 'DK': ['da'], 'FI': ['fi'], 'IS': ['is'], 'IE': ['en'], 'EE': ['et'], 'LV': ['lv'], 'LT': ['lt'],
    'RU': ['ru'], 'UA': ['uk'], 'BY': ['be', 'ru'], 'PL': ['pl'], 'CZ': ['cs'], 'SK': ['sk'], 'HU': ['hu'],
    'RO': ['ro'], 'BG': ['bg'], 'MD': ['ro', 'ru'],
    'US': ['en'], 'CA': ['en', 'fr'], 'MX': ['es'],
    'GT': ['es'], 'BZ': ['en'], 'SV': ['es'], 'HN': ['es'], 'NI': ['es'], 'CR': ['es'], 'PA': ['es'],
    'CU': ['es'], 'JM': ['en'], 'HT': ['fr', 'ht'], 'DO': ['es'], 'PR': ['es', 'en'], 'BS': ['en'], 'BB': ['en'],
    'TT': ['en'], 'AG': ['en'], 'DM': ['en'], 'GD': ['en'], 'KN': ['en'], 'LC': ['en'], 'VC': ['en'],
    'BR': ['pt'], 'AR': ['es'], 'CL': ['es'], 'CO': ['es'], 'PE': ['es'], 'VE': ['es'], 'EC': ['es'],
    'BO': ['es', 'qu', 'ay'], 'PY': ['es', 'gn'], 'UY': ['es'], 'GY': ['en'], 'SR': ['nl'],
    'EG': ['ar'], 'LY': ['ar'], 'TN': ['ar'], 'DZ': ['ar'], 'MA': ['ar'], 'SD': ['ar', 'en'], 'SS': ['en'],
    'NG': ['en'], 'GH': ['en'], 'CI': ['fr'], 'SN': ['fr'], 'ML': ['fr'], 'BF': ['fr'], 'NE': ['fr'], 'MR': ['ar', 'fr'],
    'GM': ['en'], 'GW': ['pt'], 'GN': ['fr'], 'SL': ['en'], 'LR': ['en'], 'CV': ['pt'], 'TG': ['fr'], 'BJ': ['fr'],
    'KE': ['sw', 'en'], 'ET': ['am'], 'TZ': ['sw', 'en'], 'UG': ['en', 'sw'], 'RW': ['rw', 'en', 'fr'],
    'BI': ['fr', 'rn'], 'SO': ['so', 'ar'], 'DJ': ['ar', 'fr'], 'ER': ['ti', 'ar', 'en'], 'MG': ['fr', 'mg'],
    'MU': ['en', 'fr'], 'SC': ['en', 'fr'], 'KM': ['ar', 'fr'],
    'CD': ['fr'], 'CG': ['fr'], 'CM': ['fr', 'en'], 'CF': ['fr'], 'TD': ['fr', 'ar'], 'GA': ['fr'], 'GQ': ['es', 'fr'], 'ST': ['pt'], 'AO': ['pt'],
    'ZA': ['en', 'af', 'zu', 'xh'], 'NA': ['en'], 'BW': ['en', 'tn'], 'ZW': ['en', 'sn', 'nd'], 'ZM': ['en'],
    'MW': ['en', 'ny'], 'MZ': ['pt'], 'SZ': ['en', 'ss'], 'LS': ['en', 'st'],
    'AU': ['en'], 'NZ': ['en'], 'PG': ['en', 'ho'], 'FJ': ['en', 'fj'], 'SB': ['en'], 'VU': ['en', 'fr'], 'NC': ['fr'],
    'WS': ['en', 'sm'], 'TO': ['en', 'to'], 'KI': ['en'], 'FM': ['en'], 'MH': ['en'], 'PW': ['en'], 'NR': ['en'], 'TV': ['en'],
}


def add_time_display_and_backfill(apps, schema_editor):
    """Add time_display if missing; then set time_display, flag_url, language_codes from mappings (raw SQL)."""
    import json
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        # Add time_display column only if it doesn't exist
        cursor.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() "
            "AND table_name = 'cheradip_country' AND column_name = 'time_display'"
        )
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE cheradip_country ADD COLUMN time_display VARCHAR(20) NULL")
        # Backfill time_display, flag_url, language_codes
        cursor.execute("SELECT country_code, timezone FROM cheradip_country")
        for (code, tz) in cursor.fetchall():
            tz = (tz or '').strip()
            time_display = TIMEZONE_TO_DISPLAY.get(tz) or DEFAULT_TIME_DISPLAY
            flag_url = f"https://flagcdn.com/w80/{code.lower()}.png"
            lang_json = json.dumps(COUNTRY_LANGUAGES.get(code, ['en']))
            cursor.execute(
                "UPDATE cheradip_country SET time_display = %s, flag_url = %s, language_codes = %s WHERE country_code = %s",
                [time_display, flag_url, lang_json, code],
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0010_location_remove_division_district_thana'),
    ]

    operations = [
        migrations.RunPython(add_time_display_and_backfill, noop_reverse),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='country',
                    name='time_display',
                    field=models.CharField(blank=True, max_length=20, null=True),
                ),
            ],
            database_operations=[],
        ),
    ]
