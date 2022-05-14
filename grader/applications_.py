import csv
import pprint
import re

from . import vector
from .person import Person

DEBUG_MAPPINGS = True

KNOWN_FIELDS = {
    # 'field-name' : ('alias1', 'alias2', …)

    'institute' :    ('aff-uni',
                      'institution',
                      'affiliation[uni]',
                      'University/Institute/Company'),
    'group' :        ('aff-group',
                      'affiliation[grp]',
                      'Group/Division/Department'),
    'nationality' :  ('nat',),
    'international' : ('international',),
    'name' :         ('first name',),
    'affiliation' :  ('country of affiliation',
                      'aff-state',
                      'instit loc'),
    'applied' :      ('did you already apply', 'prev-application'),
    'programming' :  ('estimate your programming skills',),
    'programming_description' : ('programming experience',),
    'python' :       ('python skills',),
    'open_source' :  ('exposure to open-source', 'opensource',),
    'open_source_description' : ('description of your contrib',),
    'motivation' :   ('appropriate course for your skill profile',),
    'cv' :           ('curriculum vitae',),
    'lastname' :     ('last name', 'surname',),
    'born' :         ('year of birth',),
    'vcs' :          ('habitually use a version control system',),
    'travel_grant' : ('travel grants', 'grants'),
}


def col_name_to_field(description, overrides):
    """Return the name of a field for this description. Must be defined.

    The double dance is because we want to map:
    - position <=> position,
    - [other] position <=> position_other,
    - curriculum vitae <=> Please type in a short curriculum vitae...
    """
    description = description.lower()

    if description[0] == description[-1] == '"':
        # why this doesn't get stripped automatically is beyond me
        description = description[1:-1]

    # E.g. "Country of Affiliation:" or "Position: [Other]"
    description = description.replace(':', '')

    # Recent versions of limesurvey set the descriptions as "KEY. Blah
    # blah" or "KEY[other]. Blah blah". Let's match the first part only.
    desc, _, _ = description.partition('.')

    m = re.match(r'(.*)\s*\[other\]', desc)
    if m:
        desc = m.group(1)
        other = '_other'
    else:
        other = ''

    if DEBUG_MAPPINGS:
        print(f'looking for {desc!r}')

    candidates = {}
    for key, aliases in overrides.items():
        assert isinstance(aliases, tuple)
        key = key.lower()
        if desc == key:
            if DEBUG_MAPPINGS:
                print('mapped exact key:', key)
            return key + other
        for alias in aliases:
            alias = alias.lower()
            if desc == alias:
                if DEBUG_MAPPINGS:
                    print('mapped alias:', alias)
                return key + other
            if alias in description:
                candidates[key] = len(alias)
                break # don't try other aliases for the same key

    if not candidates:
        if DEBUG_MAPPINGS:
            print(f'NO CANDIDATE for {desc!r}, using default name')
        return desc.lower().replace(' ', '_') + other

    if len(candidates) == 1:
        if DEBUG_MAPPINGS:
            print('one alias:', candidates)
        return list(candidates)[0] + other

    best = sorted(candidates, key=lambda k: -candidates[k])
    if candidates[best[0]] > candidates[best[1]] + 10:
        if DEBUG_MAPPINGS:
            print('best alias:', candidates)
        return best[0] + other

    print(f'NO CLEARLY BEST CANDIDATE for {description!r}: {candidates}')
    raise KeyError(description)


@vector.vectorize
def csv_header_to_fields(header, overrides):
    if DEBUG_MAPPINGS:
        print('field name overides:')
        pprint.pprint(overrides)

    failed = None
    seen = {}
    for name in header:
        try:
            conv = col_name_to_field(name, overrides)
            if DEBUG_MAPPINGS:
                print(f'MAPPING: {name!r} → {conv!r}\n')
            if conv in seen:
                raise ValueError(f'Both {name!r} and {seen[conv]!r} map to {conv!r}.')
            seen[conv] = name
            yield conv
        except KeyError as e:
            print(f"Unknown field: {name!r}")
            failed = e
    if failed:
        raise failed


@vector.vectorize
def load(file, field_name_overrides={}):
    if not hasattr(file, 'read'):
        file = open(file, encoding='utf-8-sig')

    print(f"loading '{file.name}'")
    # let's try to detect the separator
    csv_dialect = csv.Sniffer().sniff(file.read(32768))
    # manually set doublequote (the sniffer doesn't get it automatically)
    csv_dialect.doublequote = True
    # rewind
    file.seek(0)
    # now the CSV reader should be setup
    reader = csv.reader(file, dialect=csv_dialect)
    csv_header = next(reader)
    fields = csv_header_to_fields(csv_header, KNOWN_FIELDS | field_name_overrides)
    assert len(fields) == len(csv_header)      # sanity check
    assert len(set(fields)) == len(csv_header) # two columns map to the same field

    count = 0
    for entry in reader:
        if not entry:
            # skip empty line
            continue
        count += 1

        try:
            yield Person.new(fields, entry)
        except Exception as exp:
            print(f'Exception raised on entry {count}:', entry)
            print('Detected fields:\n', fields)
            raise
