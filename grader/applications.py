import collections
import csv
import itertools
import os
import pprint

from . import vector
from .util import (
    list_of_str,
    list_of_equivs,
    printf,
    our_configfile,
    open_no_newlines
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
        def female(self):
            return self.gender == 'Female'

    return Person


def fill_fields_to_col_name_section(fields_section):
    def add(k, v):
        fields_section[k] = list_of_equivs(v)
    for f in """id completed last_page_seen start_language
                date_last_action date_started
                ip_address referrer_url
                gender
                position institute group nationality
                python
                name email
                token""".split():
        add(f, f.replace('_', ' '))
    add('affiliation', "Country of Affiliation")
    add('position_other', "[Other] Position")
    add('position_other', "Position [Other]")
    add('applied', "Did you already apply")
    add('programming', "estimate your programming skills")
    add('programming_description', "programming experience")
    add('open_source', "exposure to open-source")
    add('open_source_description', "description of your contrib")
    add('motivation', "appropriate course for your skill profile")
    add('cv', "curriculum vitae")
    add('lastname', "Last name")
    add('born', "Year of birth")
    add('vcs', "Do you habitually use a Version Control System for your software projects? If yes, which one?")
    return fields_section


def col_name_to_field(description, fields_to_col_names):
    """Return the name of a field for this description. Must be defined.

    The double dance is because we want to map:
    - position <=> position,
    - [other] position <=> position_other,
    - curriculum vitae <=> Please type in a short curriculum vitae...
    """
    for key, values in fields_to_col_names.items():
        if description.lower() == key.lower():
            return key
    candidates = {}
    for key, values in fields_to_col_names.items():
        for spelling in values:
            if spelling.lower() in description.lower():
                candidates[spelling] = key
    if candidates:
        ans = candidates[sorted(candidates.keys(), key=len)[-1]]
        return ans
    raise KeyError(description)


@vector.vectorize
def parse_applications_csv_file(file, fields_to_col_names_section):
    printf("loading '{}'", file.name)
    reader = csv.reader(file)
    csv_header = next(reader)
    fields = csv_header_to_fields(csv_header, fields_to_col_names_section)
    person_factory = build_person_factory(fields)
    assert len(csv_header) == len(person_factory._fields)
    while True:
        yield person_factory(*next(reader))


@vector.vectorize
def csv_header_to_fields(header, fields_to_col_names_section):
    failed = None
    for name in header:
        try:
            yield col_name_to_field(name, fields_to_col_names_section)
        except KeyError as e:
            printf("unknown field: '{}'".format(name))
            failed = e
    if failed:
        pprint.pprint(list(fields_to_col_names_section.items()))
        raise failed


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

    def to_list(self):
        """Return the list of applicants as-is"""
        return self.applicants

    @classmethod
    def from_paths(cls, config_path, csv_path, fields_to_col_names_section):
        if os.path.exists(config_path):
            config = our_configfile(config_path)
        else:
            config = None
            printf('Warning: no configuration file found in {}', config_path)

        with open_no_newlines(csv_path) as f:
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


