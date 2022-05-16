from __future__ import annotations

import dataclasses
import datetime
import functools
import re
import math

from . import applications_ as applications

# List of valid values for fields in the Person object
# The values need to match with what is used in the application form
# You can have fields not specified here in the application form, they will
# be added to Person, but won't be managed in any way (so they are only useful
# for printing or for being evaluated in the formula

VALID_GENDER = (
    'male',
    'female',
    'other',
)

VALID_POSITION = (
    'bachelor student',
    'master student',
    'phd student',
    'post-doctorate',
    'professor',
    'technician',
    'employee',
    'other',
)

VALID_PROGRAMMING = (
    'novice/advanced beginner',
    'competent/proficient',
    'expert',
)

VALID_PYTHON = (
    'none',
    *VALID_PROGRAMMING,
)

VALID_OPEN_SOURCE = (
    'never used / never heard of it',
    'user',
    'minor contributions (bug reports, mailing lists, ...)',
    'major contributions (bug fixes, new feature implementations, ...)',
    'project membership',
)

VALID_VCS = (
    "no, i don't habitually use a vcs",
    "git",
    "other (subversion, cvs, mercurial, bazaar, etc…)",
)

_year_now = datetime.datetime.now().year

def convert_bool(value):
    """Convert "booleany" strings to bool"""
    if isinstance(value, str):
        value = value.lower()
    match value:
        case ('y' | 'yes'|'true'):
            return True
        case ('n' | 'no' | 'false' | 'n/a' | 'none'):
            return False
        case bool(value) | int(value):
            return bool(value)
        case _:
            raise ValueError(f'cannot convert {value} of type {type(value)} to bool')

@dataclasses.dataclass(kw_only=True, order=False)
class Person:
    name: str
    lastname: str
    email: str
    gender: str
    institute : str
    group: str
    affiliation: str       # this is the affiliation country
    position: str          # employment or educational status
    position_other: str    # non-empty if position=='Other'
    programming: str       # programming experience level
    programming_description: str # description of programming experience
    python: str            # python experience level
    vcs: str = 'N/A'       # used VCS (git, other, ...)
    open_source: str       # experience with open source
    open_source_description: str
    cv: str
    motivation: str
    born: int              # birth year
    nationality: str
    applied: bool          # already applied? (self-reported)

    n_applied: int = 0

    # internal attribute signaling relaxed checking
    # needed to relax value checks for old application files [should not be
    # necessary for new application files
    _relaxed: bool = dataclasses.field(default=False, repr=False)

    # internal attribute keeping a reference to the application.ini file
    _ini: applications.ApplicationsIni = \
        dataclasses.field(default=None, repr=False)

    _generation: int = dataclasses.field(default=0, repr=False)

    _score_cache: dict = dataclasses.field(default_factory=dict, repr=False)

    @property
    def motivation_scores(self):
        if self._ini is None:
            return []
        return self._ini.get_motivation_scores(self.fullname)

    def set_motivation_score(self, value, identity):
        if self._ini is None:
            raise ValueError

        self._ini.set_motivation_score(
            self.fullname, value, identity=identity)

        # The internal state has been modified, version nnn
        self._generation += 1

    @property
    def labels(self):
        if self._ini is None:
            return []
        return self._ini.get_labels(self.fullname)

    def add_label(self, label):
        if self._ini is None:
            raise ValueError

        labels = self.labels
        if label in self.labels:
            return

        labels = sorted(labels + [label])
        self._ini.set_labels(self.fullname, labels)

        self._generation += 1

    def remove_label(self, label):
        if self._ini is None:
            raise ValueError

        labels = self.labels
        if label not in self.labels:
            return

        labels.remove(label)
        self._ini.set_labels(self.fullname, labels)

        self._generation += 1

    @property
    def fullname(self) -> str:
            return f'{self.name} {self.lastname}'

    @property
    def nonmale(self) -> str:
            return self.gender.lower() != 'male'

    def __post_init__(self):
        # strip extraneous whitespace from around and within names and emails
        self.name = ' '.join(self.name.split())
        self.lastname = ' '.join(self.lastname.split())

        self._apply_overrides()

        self.email = self.email.strip()

        # only run the checks if we are in strict mode
        if self._relaxed:
            return

        if not (1900 <= self.born <= _year_now):
            raise ValueError(f'Bad birth year {self.born}')

        for field in ('gender', 'programming', 'python', 'position'):
            value = getattr(self, field).lower()
            if value not in globals()[f'VALID_{field.upper()}']:
                raise ValueError(f'Bad {field} value: {value}')

    # type-aware setattr
    def __setattr__(self, attr, value):
        # we only try to normalize the types of attributes with safe types
        allowed_types = dict(str=str,
                            bool=convert_bool,
                            float=float,
                            int=int)
        # find the type of the attr from the type annotations
        for field in dataclasses.fields(self):
            if field.name == attr:
                if typ := allowed_types.get(field.type):
                    value = typ(value)
                break
        super().__setattr__(attr, value)

        # We use the ancestor's method to avoid recursively calling our own __setattr__
        super().__setattr__('_generation', self._generation + 1)

    def _apply_override(self, attr):
        if not self._ini:
            return

        key = f'{attr}_overrides.{self.fullname.lower()}'
        if override := self._ini[key]:
            print(f'INFO: {self.fullname}: found override, setting {attr}={override}')
            setattr(self, attr, override)
            return True

    def _apply_overrides(self):
        for attr in dir(self):
            if attr.startswith('_'):
                continue

            self._apply_override(attr)

    # this is to be used when we want to create a Person from a CSV file,
    # automatically loading unknown/unprocessed fields
    @classmethod
    def from_row(cls, fields, values, relaxed=False, ini=None):
        # first instantiate a Person with the known/required fields
        known_fields = [item.name for item in dataclasses.fields(cls)]
        hard_coded = {field:value for (field, value) in zip(fields, values)
                                  if field in known_fields}
        person = cls(**hard_coded, _relaxed=relaxed, _ini=ini)

        # add all the unknown/unprocessed fields
        for (field, value) in zip(fields, values):
            if field not in known_fields:
                setattr(person, field, value)

        return person

    def set_n_applied(self, archive):
        if self._apply_override('n_applied'):
            # we don't count manually, if an override was found
            return

        found = 0
        for year in archive:
            candidates = year.filter(fullname=f'^{self.fullname}$')
            if not candidates:
                candidates = year.filter(email=self.email)

            assert len(candidates) <= 1
            if candidates:
                found += 1

        assert isinstance(self.applied, bool)

        if found and not self.applied:
            print(f'INFO: {self.fullname}: n_applied={found}, setting applied=yes')
            self.applied = True
        if not found and self.applied:
            print('WARNING: person says they applied, but not found in archive: '
                  f'{self.fullname} <{self.email}>')
            self.applied = False

        self.n_applied = found

    @property
    def score(self):
        if self._ini is None:
            return math.nan

        key = (self._generation, self._ini.generation, self._ini.formula)
        try:
            return self._score_cache[key]
        except KeyError:
            fp = FormulaProxy(self)

            v = eval(self._ini.formula, {}, fp)

            self._score_cache[key] = v
            return v

class FormulaProxy:
    def __init__(self, person):
        self.person = person
        self.rankings = person._ini.ratings()

    def __getitem__(self, name):
        if name == 'nan':
            return math.nan

        try:
            val = getattr(self.person, name)
        except AttributeError:
            val = self.person._ini[f'formula.{name}']

        if name in self.rankings:
            # Explanation in () or after / is ignored in the key
            key = re.match(r'(.+?)\s*(?:[(/,]|$)', val).group(1).lower()
            try:
                val = self.rankings[name][key]
            except KeyError:
                raise KeyError(f'{name} not rated for {key!r}')

        return val
