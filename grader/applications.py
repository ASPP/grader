import collections
import csv
import itertools
import os
import pprint
import re

from . import vector
from .util import (
    list_of_str,
    list_of_equivs,
    printf,
    our_configfile,
)


def build_person_factory(fields):
    class Person(collections.namedtuple('Person', fields)):
        def __init__(self, *args, **kwargs):
            # tuple fields are already set in __new__
            self.score = None
            self.rank = None
            self.highlander = None
            self.samelab = False
            self.labels = list_of_str()
            try:
                # manually set applied and napplied attributes,
                # in case this is the first time we run the school
                # and there are no old applications laying around
                self.napplied = 0
                self.applied = 'N'
            except AttributeError:
                # we get an "AttributeError: can't set attribute"
                # if the attributes are set already
                pass

        @property
        def fullname(self):
            return '{p.name} {p.lastname}'.format(p=self)

        @property
        def nonmale(self):
            "Return true if gender is 'female' or 'other'"
            return self.gender.lower() != 'male'

    return Person

DEBUG_MAPPINGS = False

def col_name_to_field(description, fields_to_col_names):
    """Return the name of a field for this description. Must be defined.

    The double dance is because we want to map:
    - position <=> position,
    - [other] position <=> position_other,
    - curriculum vitae <=> Please type in a short curriculum vitae...
    """
    if description[0] == description[-1] == '"':
        # why this doesn't get stripped automatically is beyond me
        description = description[1:-1]

    # E.g. "Country of Affiliation:" or "Position: [Other]"
    description = description.replace(':', '')

    # Recent versions of limesurvey set the descriptions as "KEY. Blah
    # blah" or "KEY[other]. Blah blah". Let's match the first part only.
    desc, _, _ = description.partition('.')
    desc = desc.lower()

    m = re.match('(.*)\s*\[other\]', desc)
    if m:
        desc = m.group(1)
        other = '_other'
    else:
        other = ''

    if DEBUG_MAPPINGS:
        print(f'looking for {desc!r}')

    candidates = {}
    for key, values in fields_to_col_names.items():
        if desc == key:
            if DEBUG_MAPPINGS:
                print('mapped exact key:', key)
            return key + other
        for spelling in values:
            if spelling == '':
                continue
            if desc == spelling.lower():
                if DEBUG_MAPPINGS:
                    print('mapped spelling:', spelling)
                return key + other
            if spelling.lower() in description.lower():
                candidates[key] = len(spelling)
                break # don't try other spellings for the same key

    if not candidates:
        if DEBUG_MAPPINGS:
            print(f'NO CANDIDATE for {description}')
        raise KeyError(description)

    if len(candidates) == 1:
        if DEBUG_MAPPINGS:
            print('one spelling:', candidates)
        return list(candidates)[0] + other

    best = sorted(candidates, key=lambda k: -candidates[k])
    if candidates[best[0]] > candidates[best[1]] + 10:
        if DEBUG_MAPPINGS:
            print('best spelling:', candidates)
        return best[0] + other

    print(f'NO CLEARLY BEST CANDIDATE for {description}: {candidates}')
    raise KeyError(description)

@vector.vectorize
def csv_header_to_fields(header, fields_to_col_names_section):
    if DEBUG_MAPPINGS:
        pprint.pprint(list(fields_to_col_names_section.items()))

    failed = None
    seen = {}
    for name in header:
        try:
            conv = col_name_to_field(name, fields_to_col_names_section)
            if DEBUG_MAPPINGS:
                print(f'MAPPING: {name} → {conv}\n')
            if conv in seen:
                raise ValueError(f'Both "{name}" and "{seen[conv]}" map to "{conv}".')
            seen[conv] = name
            yield conv
        except KeyError as e:
            printf(f"unknown field: '{name}'")
            failed = e
    if failed:
        raise failed

@vector.vectorize
def parse_applications_csv_file(file, fields_to_col_names_section):
    printf("loading '{}'", file.name)
    # let's try to detect the separator
    csv_dialect = csv.Sniffer().sniff(file.read(32768))
    # manually set doublequote (the sniffer doesn't get it automatically)
    csv_dialect.doublequote = True
    # rewind
    file.seek(0)
    # now the CSV reader should be setup
    reader = csv.reader(file, dialect=csv_dialect)
    csv_header = next(reader)
    fields = csv_header_to_fields(csv_header, fields_to_col_names_section)
    assert len(fields) == len(csv_header)      # sanity check
    assert len(set(fields)) == len(csv_header) # two columns map to the same field
    person_factory = build_person_factory(fields)
    assert len(csv_header) == len(person_factory._fields)
    count = 0
    while True:
        try:
            entry = next(reader)
        except StopIteration:
            return
        if not entry:
            # skip empty line
            continue
        count += 1
        try:
            yield person_factory(*entry)
        except Exception as exp:
            print("Exception raised on entry %d:"%count, exp)
            print('Detected fields:', fields)
            import pdb; pdb.set_trace()

class Applications:

    def __init__(self, applicants, config):
        self.applicants = applicants
        self.config = config

        if config is not None:
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


