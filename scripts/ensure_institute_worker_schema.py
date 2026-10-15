"""Bridge institute worker tables on legacy servers with incomplete migration history.

This deliberately changes only the institute worker's missing tables, columns,
and index. It does not mark unrelated Django migrations as applied.
Run without --apply to inspect the plan first.
"""

import argparse
import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402
from cheradip.models import (  # noqa: E402
    InstituteRefreshEvent,
    InstituteRefreshRequest,
    InstituteTeacher,
    InstituteUpdateAttempt,
    InstituteUpdateRun,
)


EXISTING_FIELDS = (
    (InstituteUpdateRun, ('schedule_month', 'retry_round', 'retry_cursor')),
    (InstituteTeacher, (
        'pds_id', 'index_no', 'district_name', 'bcs_batch',
        'joining_date', 'present_joining_date', 'photo_url',
    )),
)
NEW_MODELS = (InstituteRefreshRequest, InstituteRefreshEvent)
ATTEMPT_INDEX = 'institute_run_status_idx'


def inspect_schema():
    tables = set(connection.introspection.table_names())
    operations = []
    with connection.cursor() as cursor:
        for model, allowed_missing in EXISTING_FIELDS:
            table = model._meta.db_table
            if table not in tables:
                raise RuntimeError(f'Required existing table is absent: {table}')
            columns = {column.name for column in connection.introspection.get_table_description(cursor, table)}
            unexpected = {field.column for field in model._meta.local_fields} - columns - set(allowed_missing)
            if unexpected:
                raise RuntimeError(f'{table} has unexpected missing columns: {sorted(unexpected)}')
            for name in allowed_missing:
                field = model._meta.get_field(name)
                if field.column not in columns:
                    operations.append(('field', model, field))

        for model in NEW_MODELS:
            table = model._meta.db_table
            if table not in tables:
                operations.append(('table', model, None))
            else:
                columns = {column.name for column in connection.introspection.get_table_description(cursor, table)}
                missing = {field.column for field in model._meta.local_fields} - columns
                if missing:
                    raise RuntimeError(f'{table} exists but is incomplete: {sorted(missing)}')

        attempt_table = InstituteUpdateAttempt._meta.db_table
        if attempt_table not in tables:
            raise RuntimeError(f'Required existing table is absent: {attempt_table}')
        constraints = connection.introspection.get_constraints(cursor, attempt_table)
        if ATTEMPT_INDEX not in constraints:
            index = next(index for index in InstituteUpdateAttempt._meta.indexes if index.name == ATTEMPT_INDEX)
            operations.append(('index', InstituteUpdateAttempt, index))
    return operations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Apply the inspected, limited schema changes.')
    args = parser.parse_args()
    database_name = connection.settings_dict['NAME']
    if database_name != 'cheradip_cheradip':
        raise RuntimeError(f'Refusing to alter unexpected database: {database_name}')
    operations = inspect_schema()
    for kind, model, item in operations:
        print(f'{kind}: {model._meta.db_table}' + (f'.{item.column if kind == "field" else item.name}' if item else ''))
    if not operations:
        print('Institute worker schema is ready; no changes needed.')
        return
    if not args.apply:
        print('Dry run only. Pass --apply to make these changes.')
        return
    for kind, model, item in operations:
        with connection.schema_editor() as editor:
            if kind == 'field':
                editor.add_field(model, item)
            elif kind == 'table':
                editor.create_model(model)
            else:
                editor.add_index(model, item)
    if inspect_schema():
        raise RuntimeError('Institute worker schema remains incomplete after applying changes.')
    print('Institute worker schema is ready.')


if __name__ == '__main__':
    main()
