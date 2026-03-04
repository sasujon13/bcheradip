"""
Sync groups from cheradip_subject.groups (JSON) into Group, ClassLevel, and ClassGroupMapping
so that groups_by_class API returns Science, Humanities, Business Studies for class 9-10 and 11-12.

Group.group_code is single-char; we assign first available letter (e.g. S=Science, H=Humanities, B=Business Studies).
"""
from django.core.management.base import BaseCommand
from cheradip.models import Subject, Group, ClassLevel, ClassGroupMapping


class Command(BaseCommand):
    help = 'Sync distinct subject groups (9-10, 11-12) into Group and ClassGroupMapping'

    def handle(self, *args, **options):
        # Collect distinct group names from Subject where class_level is 9-10 or 11-12
        qs = Subject.objects.filter(class_level__in=('9-10', '11-12')).exclude(groups__isnull=True)
        all_names = set()
        for subj in qs.only('groups').iterator():
            g = subj.groups
            if isinstance(g, list):
                for name in g:
                    if name and isinstance(name, str) and name.strip():
                        all_names.add(name.strip())
            elif isinstance(g, str) and g.strip():
                all_names.add(g.strip())

        if not all_names:
            self.stdout.write(self.style.WARNING('No groups found in cheradip_subject for class 9-10 or 11-12.'))
            return

        # Assign single-letter codes (Group.group_code is max_length=1). Use first available letter per sorted name.
        used_letters = set()
        name_to_code = {}
        for name in sorted(all_names):
            # Prefer first letter of first word; if taken, try next letter of name
            for c in name.replace(' ', ''):
                letter = c.upper()
                if letter.isalpha() and letter not in used_letters:
                    name_to_code[name] = letter
                    used_letters.add(letter)
                    break
            if name not in name_to_code:
                # Fallback: use first unused letter from A-Z
                for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                    if letter not in used_letters:
                        name_to_code[name] = letter
                        used_letters.add(letter)
                        break

        # Create or update Group for each
        for name, code in name_to_code.items():
            Group.objects.update_or_create(
                group_code=code,
                defaults={'group_name': name}
            )
        self.stdout.write(f'Groups: {name_to_code}')

        # Ensure ClassLevel 9-10 and 11-12 exist with has_groups=True
        for code, label in [('9-10', 'Class 9-10'), ('11-12', 'Class 11-12')]:
            ClassLevel.objects.update_or_create(
                class_code=code,
                defaults={
                    'class_name': label,
                    'has_groups': True,
                    'has_departments': False,
                    'is_active': True,
                    'display_order': 10 if code == '9-10' else 11,
                }
            )

        # Set group_codes for 9-10 and 11-12 (comma-separated single letters)
        codes_str = ','.join(sorted(name_to_code.values()))
        for class_code in ('9-10', '11-12'):
            cl = ClassLevel.objects.get(class_code=class_code)
            existing = ClassGroupMapping.objects.filter(class_level=cl).first()
            if existing:
                existing.group_codes = codes_str
                existing.save()
            else:
                ClassGroupMapping.objects.create(class_level=cl, group_codes=codes_str)

        self.stdout.write(self.style.SUCCESS(
            f'Synced {len(name_to_code)} groups to Group; ClassLevel 9-10 and 11-12 mapped to {codes_str}'
        ))
