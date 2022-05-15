import configparser
import csv
import fnmatch
import pprint
import re

from . import vector
from .person import Person
from . import util

DEBUG_MAPPINGS = False

# CSV-file:
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

# INI-file:
# the type of the values for the items in the sections of the applications.ini file
SECTION_TYPES = {
        'labels' : util.list_of_str,
        '*_rating' : float, # all sections ending with _rating are going to be floats
        'groups_parameters' : int,
        'fields' : util.list_of_equivs,
        'motivation_score-*' : int,
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

class ApplicationsIni:
    def __init__(self, file):
        if not hasattr(file, 'read'):
            self.filename = file
            file = open(file)
        else:
            self.filename = file.name

        cp = self.config_parser()
        cp.read_file(file)

        # this keeps all the data from the INI file, ex:
        # 'motivation_score-0' : {'firstname lastname' : -1}
        self.data = {name: self.convert_section(name, section)
                     for name, section in cp.items()}

    @staticmethod
    def config_parser():
        return configparser.ConfigParser(comment_prefixes='#',
                                         inline_comment_prefixes='#')

    def _find_conv(self, section_name):
        # find the appropriate converter for a given section
        for pattern, conv in SECTION_TYPES.items():
            # find the proper type for the section naming matching pattern
            if fnmatch.fnmatch(section_name, pattern):
                return conv
        # just return as-is if we don't know the type for this section
        return lambda x: x

    def convert_section(self, section_name, section):
        conv = self._find_conv(section_name)
        # convert section item values to the proper type
        return {key:conv(value) for key, value in section.items()}

    def save(self, file=None):
        cp = self.config_parser()
        cp.read_dict(self.data)

        file = file or self.filename
        if not hasattr(file, 'write'):
            file = open(file, 'w')

        with file as fh:
            cp.write(fh)

    def __setitem__(self, key, value):
        section_name, key_name = key.split('.')
        conv = self._find_conv(section_name)
        self.data[section_name][key_name] = conv(value)

    def __getitem__(self, key):
        # The key is split into two parts: section and key name.
        # The key names are allowed to contain dots (this is what maxsplit is for).
        a, b = key.split('.', maxsplit=1)
        return self.data[a][b]

    def label_append(self, key, value):
        v = self[key].append(value)
        if v is None:
            v = []
        v += [value]
        self[key] = v


class Applications:
    def __init__(self, applicants, config):
        self.applicants = applicants
        self.config = config

        if config is not None:
            # Add overrides from config
            for section in config.sections:
                if section.endswith('_overrides'):
                    field = section[0:-len('_overrides')]
                    for fullname, value in config[section].items():
                        for idx, person in enumerate(applicants):
                            if person.fullname.lower() == fullname:
                                item = {field : value}
                                new_fields = person._replace(**item)
                                new_person = PERSON_FACTORY(**new_fields._asdict())
                                applicants[idx] = new_person

            # Add applicant labels from config file to applicant object
            for applicant in applicants:
                labels = config['labels'].get(applicant.fullname,
                                              list_of_str())
                applicant.labels = labels

    def __getitem__(self, key):
        """Support basic iteration"""
        return self.applicants[key]

    def __len__(self):
        return len(self.applicants)

    @classmethod
    def from_paths(cls, config_path, csv_path, fields_to_col_names_section):
        if os.path.exists(config_path):
            config = our_configfile(config_path)
        else:
            config = None
            printf('Warning: no configuration file {}', config_path)

        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            applicants = parse_applications_csv_file(
                f, fields_to_col_names_section)

        applications = cls(applicants, config)
        return applications

    def find_applicant_by_fullname(self, fullname):
        for applicant in self.applicants:
            if applicant.fullname.lower() == fullname.lower():
                return applicant
        else:
            raise ValueError('Applicant "{}" not found'.format(fullname))

    def add_labels(self, fullname, labels):
        # update applicant
        applicant = self.find_applicant_by_fullname(fullname)
        applicant.labels.extend(labels)
        # update config file
        section = self.config['labels']
        saved = section.get(fullname, list_of_str())
        saved.extend(labels)
        section[fullname] = saved

    def clear_labels(self, fullname):
        # update applicant
        applicant = self.find_applicant_by_fullname(fullname)
        applicant.labels = []
        # update config file
        self.config['labels'].clear(fullname)

    def get_labels(self, fullname):
        applicant = self.find_applicant_by_fullname(fullname)
        return applicant.labels

    def get_all_labels(self):
        labels = set()
        for applicant in self.applicants:
            labels.update(applicant.labels)
        return labels

    def filter(self, **kwargs):
        """Return an iterator over the applications which match certain criteria:

        Examples:

        applications.filter(nationality='Italy') -->
                            applicants where person.nationality=='Italy'

        applications.filter(label='XXX') -->
                            applicants labeled XXX

        applications.filter(label=('XXX', 'YYY')) -->
                            applicants labeled XXX and YYY

        applications.filter(label=('XXX', 'YYY', '-', 'ZZZ')) -->
                            applicants labeled XXX and YYY but not ZZZ

        applications.filter(label=('XXX', 'YYY', '-', 'ZZZ', 'WWW')) -->
                            applicants labeled XXX and YYY
                            but nor ZZZ neither WWW

        Note: returns all applications when called without arguments
        """
        # first match labels
        labels = kwargs.pop('label', None)
        if labels is not None:
            matching = []
            labels = iter((labels, )) if type(labels) == str else iter(labels)
            accept = frozenset(itertools.takewhile(lambda x: x!='-', labels))
            deny = frozenset(labels)
            for p in self.applicants:
                labels = set(p.labels)
                if not (accept - labels) and not (labels & deny):
                    matching.append(p)
        else:
            matching = self.applicants[:]

        # now filter through attributes
        for attr, value in kwargs.items():
            matching = [p for p in matching if getattr(p, attr) == value]

        return matching


