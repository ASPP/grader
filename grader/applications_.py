import csv
import pprint
import re

from . import vector
from .person import Person

DEBUG_MAPPINGS = False

# List of field names and their aliases used to match the columns in the header
# of the CSV files
KNOWN_FIELDS = {
    # 'field-name' : ('alias1', 'alias2', …)
    'email' :        ('email address',),
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


# this function does the real hard-work of parsing the CSV file
def col_name_to_field(description, overrides):
    """Return the name of a field for this description. Must be defined.

    The double dance is because we want to map:
    - position <=> position,
    - [other] position <=> position_other,
    - curriculum vitae <=> Please type in a short curriculum vitae...
    """
    # normalize to lowercase and get rid of extraneous whitespace
    description = ' '.join(description.lower().split())

    if description[0] == description[-1] == '"':
        # why this doesn't get stripped automatically is beyond me
        description = description[1:-1]

    # E.g. "Country of Affiliation:" or "Position: [Other]"
    description = description.replace(':', '')

    # Recent versions of limesurvey set the descriptions as "KEY. Blah
    # blah" or "KEY[other]. Blah blah". Let's match the first part only.
    desc, _, _ = description.partition('.')

    # match based on the different ways limesurvey implemented the 'other' value
    # in specific fields. Ex: 'Position [Other]', '[Other] Position'
    m = re.match(r'(.+?)\s*\[other\] | \[other\]\s*(.+)', desc, re.VERBOSE)
    if m:
        # use only the non empty group
        desc = m.group(1) or m.group(2)
        # use the same field name with the suffix '_other', ex: position_other
        other = '_other'
    else:
        # if we did not match, use the field name without the suffix, ex: position
        other = ''

    if DEBUG_MAPPINGS:
        print(f'looking for {desc!r}')

    # look over all the column names and find fuzzy matches to decide if one is a
    # clear fit for one of the known fields
    candidates = {}
    for key, aliases in overrides.items():
        assert isinstance(aliases, tuple)
        # normalize the name of the field
        key = key.lower()
        if desc == key:
            # we have an exact match, we can stop here
            if DEBUG_MAPPINGS:
                print('mapped exact key:', key)
            return key + other
        for alias in aliases:
            # we did not find a match for the name of the field, loop through
            # all possible aliases
            # normalize the alias for the field
            alias = alias.lower()
            if desc == alias:
                # we have a match
                if DEBUG_MAPPINGS:
                    print('mapped alias:', alias)
                return key + other
            if alias in description:
                # we found a fuzzy match, keep track of it for the moment
                candidates[key] = len(alias)
                break # don't try other aliases for the same key

    if not candidates:
        # we do not know this name, just normalize the column name and return it
        if DEBUG_MAPPINGS:
            print(f'NO CANDIDATE for {desc!r}, using default name')
        return desc.lower().replace(' ', '_') + other

    if len(candidates) == 1:
        # we have found only a fuzzy match, assume it is the right one
        if DEBUG_MAPPINGS:
            print('one alias:', candidates)
        return list(candidates)[0] + other

    # we have found several fuzzy matches, pick the one that matches the longest
    # portion of the column name and is 10 characters longer than the second best
    best = sorted(candidates, key=lambda k: -candidates[k])
    if candidates[best[0]] > candidates[best[1]] + 10:
        if DEBUG_MAPPINGS:
            print('best alias:', candidates)
        return best[0] + other

    # if we land here, we can't distinguish among the fuzzy matches, bail out
    print(f'NO CLEARLY BEST CANDIDATE for {description!r}: {candidates}')
    raise KeyError(description)


# create the mapping from the columns of the CSV header to the known fields
@vector.vectorize
def csv_header_to_fields(header, overrides):
    if DEBUG_MAPPINGS:
        print('field name overides:')
        pprint.pprint(overrides)

    failed = None
    seen = {}
    for name in header:
        try:
            # convert the current column
            conv = col_name_to_field(name, overrides)
            if DEBUG_MAPPINGS:
                print(f'MAPPING: {name!r} → {conv!r}\n')
            if conv in seen:
                # we don't want to convert two different columns to the same field
                raise ValueError(f'Both {name!r} and {seen[conv]!r} map to {conv!r}.')
            seen[conv] = name
            yield conv
        except KeyError as e:
            print(f"Unknown field: {name!r}")
            failed = e
    if failed:
        raise failed


# vectorize consumes the generator and returns a special list, which allows
# vectorized attribute access to the list elements, for example
# applications = load(file)
# applications.name -> ['Marcus', 'Lukas', 'Giovanni', ...]
@vector.vectorize
def load(file, field_name_overrides={}, relaxed=False):
    # support both file objects and path-strings
    if not hasattr(file, 'read'):
        file = open(file, encoding='utf-8-sig') ### support for CSV file with BOM

    print(f"loading '{file.name}'")
    # let's try to detect the separator
    csv_dialect = csv.Sniffer().sniff(file.read(32768))
    # manually set doublequote (the sniffer doesn't get it automatically)
    csv_dialect.doublequote = True
    # rewind
    file.seek(0)
    # now the CSV reader should be set up
    reader = csv.reader(file, dialect=csv_dialect)
    csv_header = next(reader)
    # map the columns of the header to fields
    fields = csv_header_to_fields(csv_header, KNOWN_FIELDS | field_name_overrides)

    assert len(fields) == len(csv_header)      # sanity check
    assert len(set(fields)) == len(csv_header) # two columns map to the same field

    count = 0
    for entry in reader:
        if (not entry) or len(set(entry)) <= 1:
            # first match: empty line at the beginning or at the end of the file
            # second match: empty line in the middle of the file
            continue
        count += 1

        try:
            yield Person.new(fields, entry, relaxed=relaxed)
        except Exception as exp:
            print(f'Exception raised on entry {count}:', entry)
            print('Detected fields:\n', fields)
            raise
