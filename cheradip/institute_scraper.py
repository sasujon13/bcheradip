"""Staff-run, resumable import of public institute-directory records.

The fixed Banbeis and EMIS hosts are deliberate: no browser-supplied URL is fetched.
EMIS supplies a public teacher directory; only fields used on the institute page are retained.
"""

import re
import time

import requests
from django.db import transaction
from django.utils import timezone

from .models import Banbeis, InstituteScrapePage, InstituteSourceSnapshot, InstituteTeacher, Institutes


BANBEIS_API = 'https://apigw.ieims.banbeis.gov.bd/eatl-config-service/api/v1'
EMIS_DIRECTORY = 'https://emis.gov.bd/EMIS/Portal/GetInstitute'
EMIS_TEACHERS = 'https://emis.gov.bd/EMIS/Portal/GetTeacherDetails'
SOURCE_HEADERS = {'User-Agent': 'Cheradip institute directory updater (staff-operated; contact: cheradip.com)', 'Accept': 'application/json'}
_EIIN = re.compile(r'^\d{6}$')


class InstituteSourceError(Exception):
    pass


def _json_response(response, source):
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError as exc:
        raise InstituteSourceError(f'{source} returned a non-JSON response.') from exc
    if not isinstance(data, dict):
        raise InstituteSourceError(f'{source} returned an unexpected response.')
    return data


def fetch_banbeis_page(session, page, size):
    response = session.get(
        f'{BANBEIS_API}/institute/public/list', params={'page': page, 'size': size},
        headers=SOURCE_HEADERS, timeout=20,
    )
    data = _json_response(response, 'Banbeis')
    if data.get('status') != 'success' or not isinstance(data.get('data'), list):
        raise InstituteSourceError('Banbeis list response is not in the expected format.')
    return data['data'], int((data.get('meta') or {}).get('total') or 0)


def fetch_banbeis_detail(session, eiin):
    response = session.get(
        f'{BANBEIS_API}/institute/public/find-by-eiin/{eiin}',
        headers=SOURCE_HEADERS, timeout=20,
    )
    result = _json_response(response, 'Banbeis')
    detail = result.get('data')
    if result.get('status') != 'success' or not isinstance(detail, dict) or str(detail.get('eiinNo')) != eiin:
        raise InstituteSourceError(f'Banbeis detail for {eiin} did not match its list record.')
    return detail


def fetch_emis_directory_entry(session, eiin):
    response = session.post(
        EMIS_DIRECTORY,
        data={
            'ZoneId': '', 'DistrictId': '', 'SubDistrictId': '',
            'InstituteCategoryId': '', 'ManagementTypeId': '', 'EIIN': eiin,
        },
        headers={**SOURCE_HEADERS, 'Referer': 'https://emis.gov.bd/EMIS/portalone'}, timeout=20,
    )
    result = _json_response(response, 'EMIS')
    entities = result.get('Entities') if isinstance(result, dict) else None
    if not isinstance(entities, list):
        raise InstituteSourceError('EMIS directory response is not in the expected format.')
    matches = [row for row in entities if isinstance(row, dict) and str(row.get('Eiin')) == eiin]
    if len(matches) != 1:
        return {}
    row = matches[0]
    # Keep only the directory fields required to request and verify the roster.
    return {key: row.get(key) for key in ('Id', 'Eiin', 'InstituteName', 'InstituteNameInBangla')}


def fetch_emis_teachers(session, eiin, directory):
    """Read the public teacher roster, rejecting mismatched or malformed responses."""
    if str(directory.get('Eiin')) != eiin or not directory.get('Id'):
        raise InstituteSourceError(f'EMIS institute identifier did not match EIIN {eiin}.')
    response = session.post(
        EMIS_TEACHERS,
        data={'instituteId': directory['Id'], 'EIIN': eiin, 'isTeacher': 1},
        headers={**SOURCE_HEADERS, 'Referer': 'https://emis.gov.bd/EMIS/portalone'}, timeout=30,
    )
    response.raise_for_status()
    try:
        rows = response.json()
    except ValueError as exc:
        raise InstituteSourceError('EMIS teacher roster returned non-JSON data.') from exc
    if not isinstance(rows, list) or len(rows) > 1000:
        raise InstituteSourceError('EMIS teacher roster has an unexpected format or size.')
    expected_name = ' '.join(str(directory.get('InstituteNameInBangla') or '').split())
    teachers = []
    seen_ids = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or row.get('Id') is None:
            raise InstituteSourceError('EMIS teacher roster contains an invalid row.')
        source_id = str(row['Id']).strip()
        if not source_id or source_id in seen_ids:
            raise InstituteSourceError('EMIS teacher roster has duplicate or blank row IDs.')
        seen_ids.add(source_id)
        roster_name = ' '.join(str(row.get('InstituteInstituteNameInBangla') or '').split())
        if expected_name and roster_name != expected_name:
            raise InstituteSourceError(f'EMIS teacher roster did not match institute {eiin}.')
        name = _clean(row.get('FullName'), 255) or ''
        name_bn = _clean(row.get('FullNameBn'), 255) or ''
        if not name and not name_bn:
            raise InstituteSourceError('EMIS teacher roster contains a nameless row.')
        teachers.append({
            'source_row_id': source_id, 'name': name or name_bn, 'name_bn': name_bn,
            'designation': _clean(row.get('DesignationNameBn'), 255) or '',
            'subject': _clean(row.get('SubjectName'), 255) or '',
            'mobile': _clean(row.get('MobileNo'), 32) or '',
            'email': _clean(row.get('Email'), 254) or '', 'position': index,
        })
    return teachers


def sync_emis_teachers(eiin, teachers):
    """Upsert an entire verified roster. An empty response never removes old entries."""
    counts = {'created': 0, 'updated': 0, 'unchanged': 0, 'unlisted': 0}
    if not teachers:
        return counts
    now = timezone.now()
    with transaction.atomic(using='default'):
        existing = {teacher.source_row_id: teacher for teacher in
                    InstituteTeacher.objects.select_for_update().filter(eiin=eiin)}
        seen_ids = set()
        for row in teachers:
            source_id = row['source_row_id']
            if source_id in seen_ids:
                raise InstituteSourceError('EMIS teacher roster contains duplicate row IDs.')
            seen_ids.add(source_id)
            values = {key: value for key, value in row.items() if key != 'source_row_id'}
            current = existing.get(source_id)
            if current is None:
                InstituteTeacher.objects.create(eiin=eiin, source_row_id=source_id,
                                                listed=True, last_seen_at=now, **values)
                counts['created'] += 1
            else:
                changes = {key: value for key, value in values.items() if getattr(current, key) != value}
                if not current.listed:
                    changes['listed'] = True
                current.last_seen_at = now
                if changes:
                    for key, value in changes.items():
                        setattr(current, key, value)
                    current.save(update_fields=[*changes, 'last_seen_at'])
                    counts['updated'] += 1
                else:
                    current.save(update_fields=['last_seen_at'])
                    counts['unchanged'] += 1
        stale = [row for source_id, row in existing.items() if source_id not in seen_ids and row.listed]
        if stale:
            counts['unlisted'] = InstituteTeacher.objects.filter(pk__in=[row.pk for row in stale]).update(listed=False)
    return counts


def _clean(value, limit):
    if value is None:
        return None
    text = str(value).strip()
    if not text or '*' in text:  # Never persist masked telephone numbers from list results.
        return None
    return text[:limit]


def _fields_from_detail(detail, emis):
    values = {}
    source_fields = {
        'instituteName': ('instituteName', 255),
        'instituteNameBn': ('instituteNameBn', 255),
        'mobile': ('mobile', 15),
        'mobileAlternate': ('mobileAlternate', 15),
        'email': ('email', 100),
        'divisionNameBn': ('divisionNameBn', 100),
        'divisionName': ('divisionName', 100),
        'districtNameBn': ('districtNameBn', 100),
        'districtName': ('districtName', 100),
        'thanaNameBn': ('thanaNameBn', 100),
        'thanaName': ('thanaName', 100),
        'instituteTypeNameBn': ('instituteTypeNameBn', 100),
        'instituteTypeName': ('instituteTypeName', 100),
        'mouzaNameBn': ('mouzaNameBn', 255),
    }
    for field, (source, limit) in source_fields.items():
        value = _clean(detail.get(source), limit)
        if value:
            values[field] = value
    if not values.get('instituteName'):
        name = _clean(emis.get('InstituteName'), 255)
        if name:
            values['instituteName'] = name
    if not values.get('instituteNameBn'):
        name = _clean(emis.get('InstituteNameInBangla'), 255)
        if name:
            values['instituteNameBn'] = name
    if detail.get('id') is not None:
        try:
            values['id'] = int(detail['id'])
        except (TypeError, ValueError):
            pass
    management = _clean(detail.get('managementNameBn') or detail.get('managementName'), 100)
    if management in {'সরকারি', 'Government', 'Govt.', 'Govt'}:
        values['isGovt'] = True
    elif management in {'বেসরকারি', 'Non-Government', 'Non Government', 'Private'}:
        values['isGovt'] = False
    return values


def _fill_existing_english_labels(values):
    """Reuse established local bilingual labels for newly discovered EIINs."""
    scopes = {
        'divisionName': ('divisionNameBn', {}),
        'districtName': ('districtNameBn', {'divisionNameBn': values.get('divisionNameBn')}),
        'thanaName': ('thanaNameBn', {'districtNameBn': values.get('districtNameBn')}),
        'instituteTypeName': ('instituteTypeNameBn', {}),
    }
    for english, (bengali, scope) in scopes.items():
        if values.get(english) or not values.get(bengali):
            continue
        filters = {bengali: values[bengali], **{key: val for key, val in scope.items() if val}}
        translated = (Institutes.objects.filter(**filters).exclude(**{f'{english}__isnull': True})
                      .exclude(**{english: ''}).values_list(english, flat=True).first())
        values[english] = translated or values[bengali]


def _update_legacy_address(eiin, detail):
    """Refresh only address fields that already appear on the institute page."""
    source_fields = {
        'PostOffice': ('postOfficeNameBn', 127),
        'PostCode': ('postOfficeCode', 7),
        'WardNo': ('wardNo', 7),
    }
    values = {field: value for field, (source, limit) in source_fields.items()
              if (value := _clean(detail.get(source), limit))}
    if not values:
        return False
    current = Banbeis.objects.select_for_update().filter(EIIN=int(eiin)).first()
    if current is None:
        return False
    changes = {field: value for field, value in values.items() if getattr(current, field) != value}
    if changes:
        for field, value in changes.items():
            setattr(current, field, value)
        current.save(update_fields=list(changes))
    return bool(changes)


def save_institute(eiin, detail, emis):
    """Update only source-provided fields; preserve older data absent upstream."""
    values = _fields_from_detail(detail, emis)
    if not values.get('instituteName') and not values.get('instituteNameBn'):
        raise InstituteSourceError(f'No institute name for {eiin}.')
    # The legacy institute table is routed to `job`; the source snapshot below
    # is in `default`. Each write is idempotent so a retry repairs either side
    # if the process stops between the two databases.
    with transaction.atomic(using='job'):
        current = Institutes.objects.select_for_update().filter(eiinNo=eiin).first()
        if current is None:
            _fill_existing_english_labels(values)
            Institutes.objects.create(eiinNo=eiin, **values)
            outcome = 'created'
        else:
            changes = {key: value for key, value in values.items() if getattr(current, key) != value}
            if changes:
                for key, value in changes.items():
                    setattr(current, key, value)
                current.save(update_fields=list(changes))
                outcome = 'updated'
            else:
                outcome = 'unchanged'
        if _update_legacy_address(eiin, detail) and outcome == 'unchanged':
            outcome = 'updated'
    with transaction.atomic(using='default'):
        snapshot, _ = InstituteSourceSnapshot.objects.select_for_update().get_or_create(eiin=eiin)
        snapshot.banbeis = detail
        snapshot.last_banbeis_sync_at = timezone.now()
        fields = ['banbeis', 'last_banbeis_sync_at', 'updated_at']
        if emis:
            snapshot.emis = emis
            snapshot.last_emis_sync_at = timezone.now()
            fields += ['emis', 'last_emis_sync_at']
        snapshot.save(update_fields=fields)
    return outcome


def process_institute_page(*, page, size, enrich_emis, apply, actor=None, session=None, eiin=None):
    session = session or requests.Session()
    if eiin is not None:
        if not _EIIN.fullmatch(eiin):
            raise InstituteSourceError('A single-institute update requires a six-digit EIIN.')
        rows, total = [{'eiinNo': eiin}], 1
    else:
        rows, total = fetch_banbeis_page(session, page, size)
    result = {'page': page, 'size': size, 'sourceTotal': total, 'created': 0, 'updated': 0,
              'unchanged': 0, 'failed': 0, 'emisSkipped': 0, 'teachersCreated': 0,
              'teachersUpdated': 0, 'teachersUnlisted': 0, 'records': [], 'applied': apply}
    for row in rows[:size if apply else 3]:
        eiin = str(row.get('eiinNo') or '').strip()
        if not _EIIN.fullmatch(eiin):
            result['failed'] += 1
            result['records'].append({'eiin': eiin, 'status': 'skipped', 'detail': 'Invalid EIIN.'})
            continue
        try:
            detail = fetch_banbeis_detail(session, eiin)
            emis = {}
            teachers = []
            emis_warning = ''
            if enrich_emis:
                try:
                    emis = fetch_emis_directory_entry(session, eiin)
                    if emis:
                        teachers = fetch_emis_teachers(session, eiin, emis)
                        if not teachers:
                            emis_warning = 'EMIS returned an empty teacher roster; existing records were kept.'
                    else:
                        emis_warning = 'No matching EMIS directory entry.'
                except (requests.RequestException, InstituteSourceError, ValueError) as exc:
                    emis_warning = str(exc)[:180]
                if emis_warning:
                    result['emisSkipped'] += 1
            outcome = save_institute(eiin, detail, emis) if apply else 'preview'
            if apply:
                result[outcome] += 1
                if teachers:
                    teacher_counts = sync_emis_teachers(eiin, teachers)
                    result['teachersCreated'] += teacher_counts['created']
                    result['teachersUpdated'] += teacher_counts['updated']
                    result['teachersUnlisted'] += teacher_counts['unlisted']
            result['records'].append({
                'eiin': eiin, 'name': detail.get('instituteName') or detail.get('instituteNameBn'),
                'emisName': emis.get('InstituteName') or '', 'status': outcome,
                'hasContact': bool(detail.get('mobile') or detail.get('email')),
                'emisWarning': emis_warning, 'teacherCount': len(teachers),
            })
        except (requests.RequestException, InstituteSourceError, ValueError) as exc:
            result['failed'] += 1
            result['records'].append({'eiin': eiin, 'status': 'failed', 'detail': str(exc)[:180]})
        if apply:
            time.sleep(0.15)
    if apply and not result['failed'] and eiin is None:
        InstituteScrapePage.objects.update_or_create(
            source='banbeis', page=page, size=size,
            defaults={'created': result['created'], 'updated': result['updated'],
                      'unchanged': result['unchanged'], 'failed': 0,
                      'source_total': total, 'processed_by': actor},
        )
    result['nextPage'] = page + 1 if not result['failed'] and eiin is None else page
    return result
