import collections
import configparser
import contextlib
import csv
from fnmatch import fnmatch
import functools
import io
import itertools
import keyword
import locale
import math
import pprint
import re
import token
import tokenize

from . import (person, vector, util)
from .util import printff


@contextlib.contextmanager
def override_locale(category, locale_string):
    # Context manager to set locale temporarily.
    # Strangely, it seems that there is no builtin that does that.
    prev_locale_string = locale.getlocale(category)
    locale.setlocale(category, locale_string)
    yield
    locale.setlocale(category, prev_locale_string)


DEBUG_MAPPINGS = False

# CSV-file:
# List of field names and their aliases, i.e. the way those fields were called
# in some past editions
# This mapping is used to match the columns in the header of the CSV files
# Start here if you want to add a new field
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
# These types will be enforced by ApplicationsIni.read_config_file
SECTION_TYPES = {
        'labels' : util.list_of_str,
        '*_rating' : float, # all sections ending with _rating are going to be floats
        'groups_parameters' : int,
        'fields' : util.list_of_equivs,
        'motivation_score-*' : int,
        }

KNOWN_GENDER_LABELS = {
    'female'    : 'F',
    'male'      : 'M',
    'other'     : 'O',
    'non-binary': 'O',
    ''          : 'U', # unknown
    'prefer not to say' : 'U'
}

SCORE_RANGE = (-1, 0, 1)

def find_names(formula):
    g = tokenize.tokenize(io.BytesIO(formula.encode('utf-8')).readline)
    return set(tokval for toknum, tokval, _, _, _  in g
                      if toknum == token.NAME and not keyword.iskeyword(tokval))

# This function does the real hard-work of parsing the CSV header to map columns
# to known fields
def col_name_to_field(description, overrides):
    """Return the name of a field for this description. Must be defined.

    The double dance is because we want to map:
    - position <=> position,
    - [other] position <=> position_other,
    - curriculum vitae <=> Please type in a short curriculum vitae...
    """
    # normalize to lowercase and get rid of extraneous whitespace
    description = ' '.join(description.lower().split())

    # remove double quotes from around the string
    if description[0] == description[-1] == '"':
        # why this doesn't get stripped automatically is beyond me
        description = description[1:-1]

    # E.g. "Country of Affiliation:" or "Position: [Other]"
    description = description.replace(':', '')

    # Recent versions of limesurvey set the descriptions as "KEY. Blah
    # blah" or "KEY[other]. Blah blah". Let's match the first part only.
    # The format is like this when you export fro limesurvey the code as well
    # as the text of the question
    desc = description.split('.', maxsplit=1)[0]

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
# uses col_name_to_field to do the hard work
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
# applications = load_applications_csv(file)
# applications.name -> ['Marcus', 'Lukas', 'Giovanni', ...]
@vector.vectorize
def load_applications_csv(file, field_name_overrides={}, relaxed=False, ini=None):
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
            yield person.Person.from_row(fields, entry, relaxed=relaxed, ini=ini)
        except Exception:
            print(f'Exception raised on entry {count}:', entry)
            print('Detected fields:\n', fields)
            raise


# This object allow access to the INI file, which contains Person's specific data
# which is generated by us, like labels and motivation scores, together with other
# parameters which are relevant for the interpretation of data from the CSV, like
# the muercial ratings assigned to certain skill levels, the formula to calculate
# the score and the ranking of the applicants.
class ApplicationsIni:
    def __init__(self, file):
        if hasattr(file, 'read'):
            # we got passed some form of file object (we may be running in a test)
            # we should now artificially hamper our performance so that controlling
            # authorities don't get mad at us [ (C) Volkswagen ]
            # file is already open
            self.filename = file.name
            # we don't know the modification time
            self.mtime = None
        else:
            # we just got a file name (hopefully a pathlib.Path object)
            self.filename = file

            # open the file for reading, if it exists
            try:
                file = open(file)
                print(f"loading '{self.filename}'")
            except FileNotFoundError:
                # if the file doesn't exist yet, we'll create it when writing
                #print(f'warning: {e}')
                file = None
                # set the modification time to the beginning of the Epoch, so that
                # any change will trigger our reload rule
                self.mtime = 0
            else:
                # store the modification time (in ns) of the file
                self.mtime = self.filename.stat().st_mtime_ns

        # Track modifications to the global state, i.e. the parameters
        # that apply to all people. Some per-person modifications are tracked
        # without changing the global generation number.
        self.generation = 0
        self.modifications_without_generation = False

        # use config parser to give us a mapping:
        # { section_names : {keys : values} }
        # where the values are already converted to the proper types
        self.data = self.read_config_file(file)

    @vector.dictify
    def read_config_file(self, file):
        self.config_file_generation = self.generation
        self.modifications_without_generation = False

        cp = configparser.ConfigParser(comment_prefixes='#', inline_comment_prefixes='#')

        if file is not None:
            cp.read_file(file)

        # this keeps all the data from the INI file, ex:
        # 'motivation_score-0' : {'firstname lastname' : -1}
        # while converting the values of the keys to the types
        # declared in SECTION_TYPES
        for section_name, section in cp.items():
            # find the type of this particular section
            typ = self._find_typ(section_name)
            yield (section_name, {key:typ(value) for key, value in section.items()})

    def has_modifications(self):
        return (self.modifications_without_generation
                or
                self.generation > self.config_file_generation)

    def _find_typ(self, section_name):
        # find the appropriate converter for a given section
        for pattern, typ in SECTION_TYPES.items():
            # find the proper type for the section naming matching pattern
            if fnmatch(section_name, pattern):
                return typ
        # just return as-is if we don't know the type for this section
        return lambda x: x

    def reload_if_modified(self):
        # this function reloads the INI file if its modified time is newer than
        # the last one the function was called. It is not called automatically
        # here. It is meant to be used in some form of command/event-loop from
        # Grader itself

        if self.mtime is None:
            # we won't reload something we can't get the modification time of
            return False

        # guard against accidentally removing the file under our feet
        try:
            current = self.filename.stat().st_mtime_ns
        except FileNotFoundError:
            print(f'WARNING: {self.filename!r} was removed')
            return False

        # don't need to reload
        if current == self.mtime:
            return False

        # if we are here, we have to reload the file
        self.mtime = current

        # unconditionally update our generation counter, because anything may
        # have been modified in the file
        self.generation += 1

        self.data = self.read_config_file(self.filename.open())

        return True

    @functools.cache
    @vector.vectorize
    def identities(self):
        """Return a vector of all identities used in the ini file"""
        for section_name, section in self.data.items():
            match section_name.split('-', maxsplit=1):
                case ('motivation_score', identity):
                    yield identity

    #@functools.cache
    def get_ratings(self, field):
        """Return a mapping:  {value → rating}. we expect the field without
        the suffix _rating"""
        for section_name, section in self.data.items():
            match section_name.rsplit('_', maxsplit=1):
                case (name, 'rating'):
                    if field == name:
                        # section is already a dictionary
                        return section
        return None

    def save(self, filename=None):
        filename = filename or self.filename
        with open(filename, 'wt') as file:
            self.save_to_file(file)

    def save_to_file(self, file):
        # save our data to the INI file
        cp = configparser.ConfigParser(comment_prefixes='#', inline_comment_prefixes='#')

        with override_locale(locale.LC_COLLATE, 'en_US.UTF-8'):
            # The order of sections is kept stable.
            #
            # Within a section, we sort the fields alphabetically,
            # with the en_US.UTF-8 collation, which puts accented
            # letters in the expected place, usually right after the
            # unaccented version.
            sorted_data = {
                name:{
                    k:values[k] for k in sorted(values,
                                                key=functools.cmp_to_key(locale.strcoll))
                }
                for name, values in self.data.items()
            }

        cp.read_dict(sorted_data)
        cp.write(file)

        name = getattr(file, 'name', '(tmp)')
        printff(f'Saved changes to {name}')


    def __setitem__(self, key, value):
        # allow to set items in the section of the INI using a dotted form, for ex:
        # to set [python_rating] -> competent = 1 you can do
        # ApplicationsIni['python_rating.competent'] = 1
        section_name, key_name = key.split('.')

        if section_name not in self.data:
            # create a new section if we don't find one in the INI
            self.data[section_name] = {}

        # enforce types for sections we know the type of
        typ = self._find_typ(section_name)
        self.data[section_name][key_name] = typ(value)

        # We increase the generation number, for modifications of the state,
        # but not for the per-person settings in [motivation-*] and [labels],
        # because those modifications increase the generation number in Person,
        # and if we increased the generation here, we would trigger recalculation
        # of scores of all people whenever one person's score or labels were modified.
        if section_name.startswith(('motivation_score-', 'labels')):
            self.modifications_without_generation = True
        else:
            self.generation += 1

    def __getitem__(self, key):
        # same as in __setattr__, allows access to section keys via a dotted notation
        # The key is split into two parts: section and key name.
        # The key names are allowed to contain dots (this is what maxsplit is for).
        if '.' in key:
            section_name, item = key.split('.', maxsplit=1)
            section = self.data.get(section_name)
            if section is None:
                ans = None
            else:
                ans = section.get(item)
        else:
            ans = self.data.get(key)
        # print(f'Query {key} -> {ans}')
        return ans

    @vector.vectorize
    def get_motivation_scores(self, fullname):
        # get all motivation scores of a Person
        for identity in self.identities():
            yield self.get_motivation_score(fullname, identity)

    def get_motivation_score(self, fullname, identity):
        # get the motivation score of a Person as assigned to them by identity
        section_name = f'motivation_score-{identity}'
        key = fullname.lower()
        return self[f'{section_name}.{key}']

    def set_motivation_score(self, fullname, value, identity):
        section_name = f'motivation_score-{identity}'
        key = fullname.lower()
        self[f'{section_name}.{key}'] = value

    def get_labels(self, fullname):
        key = fullname.lower()
        return self[f'labels.{key}'] or []

    def add_label(self, fullname, label):
        old_labels = set(self.get_labels(fullname))
        if label in old_labels:
            return False

        old_labels.add(label)
        self.set_labels(fullname, sorted(old_labels))
        return True

    def remove_label(self, fullname, label):
        old_labels = set(self.get_labels(fullname))
        if label not in old_labels:
            return False

        old_labels.remove(label)
        self.set_labels(fullname, sorted(old_labels))
        return True

    def set_labels(self, fullname, labels):
        key = fullname.lower()

        old_labels = set(self.get_labels(fullname))
        new_labels = set(labels)
        mod = old_labels == new_labels

        if not new_labels:
            self.data['labels'].pop(key)
        else:
            # write new labels
            self[f'labels.{key}'] = sorted(labels)
        return mod

    @property
    def formula(self):
        return self['formula.formula'] or 'nan'

    @formula.setter
    def formula(self, formula):
        self['formula.formula'] = formula

    @property
    def location(self):
        return self['formula.location']

    @location.setter
    def location(self, location):
        self['formula.location'] = location


# This class is a collection of applications for an edition of the school
# It can be iterated over and it can return a subset of applications matching
# certain criteria (see "filter" method)
# It keeps a reference to the INI file (if any) corresponding to the CSV file
# where applications are stored
class Applications:
    def __init__(self, csv_file, ini_file=None, relaxed=False):
        if ini_file is None:
            # if the name of the INI file is not passed explicitly, just assume
            # it is the same name as the CSV file
            ini_file = csv_file.with_suffix('.ini')
        self.ini = ApplicationsIni(ini_file)

        # load the applications from the CSV file and adjusting the overrides,
        # the labels and the motivation scores as found in the INI file
        # self.people is a list of Person objects
        self.people = load_applications_csv(csv_file,
                                            ini=self.ini,
                                            relaxed=relaxed)

        self.check_formula()

    @functools.cache
    def all_nationalities(self):
        return set(p.nationality for p in self.people)

    @functools.cache
    def all_affiliations(self):
        return set(p.affiliation for p in self.people)

    def all_labels(self):
        return set(l
                   for p in self.people
                   for l in p.labels)

    def __getitem__(self, key):
        """Get people by numerical index or by fullname"""
        # we want to be able to do applications[0] and application["mario rossi"]
        match key:
            case int(key):
                return self.people[key]
            case str(key):
                filtered = self.filter(fullname=f'^{key.lower()}$')
                match len(filtered):
                    case 1:
                        return filtered[0]
                    case 0:
                        raise IndexError(f"No person with name {key}")
                    case _:
                        raise IndexError(f"Multiple people with name {key}")
            case _:
                raise TypeError

    def __len__(self):
        return len(self.people)

    def check_formula(self, formula=None):
        if not self.people:
            return

        # We check with just one person, because if it works with
        # one person, it should work with all.
        person = self.people[0]
        person.calculate_score(formula)

    def filter(self, **kwargs):
        """Return a sequence of applications which match certain criteria:

        The returned object is a vector, i.e it can be used to extract list of
        Person attributes, like:

        names_of_italians = applications.filter(nationality='Italy').fullname

        Examples:

        applications.filter(nationality='Italy') -->
                            applicants where person.nationality=='Italy'

        applications.filter(applied=True) -->
                            people who declared that they applied already

        applications.filter(label='XXX') -->
                            applicants labeled XXX

        applications.filter(label=('XXX', 'YYY')) -->
                            applicants labeled XXX and YYY

        applications.filter(label=('XXX', 'YYY', '-', 'ZZZ')) -->
                            applicants labeled XXX and YYY but not ZZZ

        applications.filter(label=('XXX', 'YYY', '-', 'ZZZ', 'WWW')) -->
                            applicants labeled XXX and YYY
                            but nor ZZZ neither WWW

        Labels are checked exactly, and other attributes are interpreted
        as a case-insensitive regexp.

        Note: returns all applications when called without arguments
        """
        # first match labels
        # The following code is some sort of magic that nt even Zbyszek could
        # remember how it worked. It still seems to work, but super-human skills
        # may be required to modify it.
        labels = kwargs.pop('label', None)
        if labels is not None:
            matching = []
            labels = iter((labels, )) if type(labels) == str else iter(labels)
            accept = frozenset(itertools.takewhile(lambda x: x!='-', labels))
            deny = frozenset(labels)
            for p in self.people:
                labels = set(p.labels)
                if not (accept - labels) and not (labels & deny):
                    matching.append(p)
        else:
            matching = self.people[:]

        # now filter through attributes
        for attr, value in kwargs.items():
            if isinstance(value, str):
                matching = [p for p in matching
                            if re.search(value, getattr(p, attr),
                                         re.IGNORECASE)]
            else:
                matching = [p for p in matching
                            if value == getattr(p, attr)]

        return vector.vector(matching)

    def fuzzy_fullname_filter(self, value):
        """
        Checks if a subset of the full name is contained in some previous applications (or vice-versa)

        The function takes in a certain value, it expects a full name string, with multiple words.
        
        Returns a list of person objects
        """
        current_set = set(value.split())
        matching = []
        for p in self.people:
            past_set = set(p.fullname.split())
            if current_set.issubset(past_set) or past_set.issubset(current_set):
                matching.append(p)

        return matching

    def all_applied(self):
        s = set(p.n_applied for p in self.people)
        return sorted(s)

    def find_min_max(self):
        formula = self.ini.formula
        location = self.ini.location
        programming = self.ini.get_ratings('programming')
        open_source = self.ini.get_ratings('open_source')
        python = self.ini.get_ratings('python')
        vcs = self.ini.get_ratings('vcs')
        underrep = self.ini.get_ratings('underrep')
        all_applied = self.all_applied()
        all_nationalities = self.all_nationalities()
        all_affiliations = self.all_affiliations()

        # Labels are excluded from this list, they add "extra" points.
        # And we would have to test all combinations of labels, which can be slow.

        # Limit the list of nationalities and affiliations by picking only the ones
        # that are indeed used in the formula. Note that to estimate the contributions
        # of terms in the formula that explicitly reference one country, for example
        # nationality=='Egypt' if we want to favour Egyptians applicants, we really
        # need to have this string in the list of possible nationalities and affiliation
        # to evaluate the formula on.
        # We need to initialize with at least two non existing countries so that, in
        # case the formula does not contain any explicitly named country,  we still
        # have something to compare with and to differentiate among, for example for
        # terms like  nationality=!affiliation.
        # Also add location so that we take care of terms like nationality!=location
        nationalities = ['NOWHERE', 'NOWHERE2', location]
        affiliations = ['NOWHERE', 'NOWHERE2', location]
        for country in (all_nationalities | all_affiliations):
            country_str = (f"'{country}'", '"{country}"')
            found = False
            for test_str in country_str:
                if test_str in formula:
                    found = True
            if found and (country != location):
                # no need to add location again
                nationalities.append(country)
                affiliations.append(country)

        choices = dict(
            born=(1900, 2012),
            gender=tuple(set(KNOWN_GENDER_LABELS.values())),
            nonmale=(0, 1),
            applied=(0, max(all_applied)),
            nationality=nationalities,
            affiliation=affiliations,
            location=(location,),
            motivation=SCORE_RANGE,
            programming=programming.values(),
            open_source=open_source.values(),
            python=python.values(),
            vcs=vcs.values(),
            underrep=underrep.values(),
            labels=())

        to_set = find_names(formula)
        needed = [[(n, v) for v in choices[n]] for n in to_set]
        combinations = tuple(itertools.product(*needed))

        candidate = self.people[0]
        proxies = [person.FormulaProxy(candidate, overrides=dict(combo))
                   for combo in combinations]
        scores = [p.evaluate(formula) for p in proxies]
        if not scores:
            return math.nan, math.nan, dict(nan=math.nan)

        minsc = min(scores)
        maxsc = max(scores)
        # scorporate in single contributions
        items = collections.OrderedDict()
        for item in formula.split('+'):
            scores = [p.evaluate(item) for p in proxies]
            max_ = max(scores)
            min_ = min(scores)
            items[item] = (max_-min_) / (maxsc-minsc)*100
        return minsc, maxsc, items
