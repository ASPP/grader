from __future__ import annotations

import dataclasses
import datetime
import re
import math

from . import (applications, vector)

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
    """The Person class hold all information about an applicant

       The attributes are typed, but types will be only enforced for "safe" types,
       like str, bool, int, float.

       If instantiated with a reference to a INI file, Person will get all attributes
       found in the INI file corresponding to their fullname.

       Person has methods to set and read motivation scores and labels.
       To calculate the score Person uses FormulaProxy and the formula as found
       in the INI file.

       Person caches expensive properties, like score. The cache is invalidated
       and the properties computed again if changes are detected in Person or in
       the INI file such would affect the value of the property.
    """
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

    n_applied: int = 0     # this is computed based on the archives from past
                           # editions
    underrep: str = ''     # underrepresentaiton
    travel_grant: str = '' # if poor then too bad!
    # Internal attribute signaling relaxed checking.
    # Needed to relax value checks for old application files (should not be
    # necessary for new application files).
    _relaxed: bool = dataclasses.field(default=False, repr=False)

    # Internal attribute keeping a reference to the application.ini file
    _ini: applications.ApplicationsIni = \
        dataclasses.field(default=None, repr=False)

    # generation counter used to detect changes in Person that need to trigger
    # cached properties invalidation
    _generation: int = dataclasses.field(default=0, repr=False)

    # cache dict for the calls to 'score'
    _score_cache: dict = dataclasses.field(default_factory=dict, repr=False)

    @property
    def motivation_scores(self):
        if self._ini is None:
            return vector.vector()
        return self._ini.get_motivation_scores(self.fullname)

    def get_motivation_score(self, identity):
        if self._ini is None:
            return math.nan
        return self._ini.get_motivation_score(self.fullname, identity)


    def get_rating(self, name):
        ratings = self._ini.get_ratings(name)
        if ratings is None:
            raise AttributeError(f'There is no {name!r} rating in ini')

        val = getattr(self, name)
        # In some years, we don't ask some questions, so the attribute
        # containing the answer for a rating might be an empty string.
        # In that case, this rating cannot be used in the formula.
        if not val:
            return math.nan

        if not val and not ratings:
            return math.nan

        # The values of these attributes need to converted to their numerical
        # value as found in the INI file. For example from
        # Person.open_source -> "Minor Contributions (bug reports, mailing lists, ...)"
        # we extract "minor contributions" and look for it in the INI file ratings:
        # [open_source_rating]
        # ...
        # minor contributions = 0.5
        # ...
        # The rule is to match anything until the first "/" or "(" or ","
        # and removing trailing whitespace if any.
        key = re.match(r'(.+?)\s*(?:[(/,]|$)', val).group(1).lower()

        if (val := ratings.get(key)) is not None:
            return val

        raise KeyError(f'{name} not rated for {key!r}')


    def set_motivation_score(self, value, identity):
        if self._ini is None:
            raise ValueError

        self._ini.set_motivation_score(
            self.fullname, value, identity=identity)

        # The internal state has been modified, increase generation number
        self._generation += 1

    @property
    def labels(self):
        if self._ini is None:
            return []
        return self._ini.get_labels(self.fullname)

    def add_label(self, label):
        if self._ini is None:
            raise ValueError

        mod = self._ini.add_label(self.fullname, label)

        if mod:
            # The internal state has been modified, increase generation number
            self._generation += 1
        return mod

    def remove_label(self, label):
        if self._ini is None:
            raise ValueError

        mod = self._ini.remove_label(self.fullname, label)

        if mod:
            # The internal state has been modified, increase generation number
            self._generation += 1
        return mod

    @property
    def fullname(self) -> str:
            return f'{self.name} {self.lastname}'

    @property
    def nonmale(self) -> str:
            return self.gender.lower() != 'male'

    def __post_init__(self):
        # This is run once at instantiation after __init__

        # strip extraneous whitespace from around and within names and emails
        self.name = ' '.join(self.name.split())
        self.lastname = ' '.join(self.lastname.split())

        # load overrides of out own fields if any are found in the INI file
        self._apply_overrides()

        # ensure valid email
        self.email = self.email.strip()

        # only run the sanity checks if we are in strict mode
        if self._relaxed:
            return

        # we won't accept vampires or zombies.
        # we accept newborns, but not people who are not born yet
        if not (1900 <= self.born <= _year_now):
            raise ValueError(f'Bad birth year {self.born}')

        # check known fields against legal values
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
                    # enforce type
                    value = typ(value)
                break

        # set the attribute using the ancestor's method to avoid  recursively
        # calling our own __setattr__
        super().__setattr__(attr, value)
        # we are setting a new attribute, so we increase the generation
        super().__setattr__('_generation', self._generation + 1)

    def _apply_overrides(self):
        if not self._ini:
            # cannot apply overrides if there is no INI file
            return
        # loop through all public attributes
        for attr in dir(self):
            if attr.startswith('_'):
                # skip private attributes
                continue
            # create the key name for this attribute override
            key = f'{attr}_overrides.{self.fullname.lower()}'
            if override := self._ini[key]:
                # if a override for this attribute is found, we override the
                # field as reported by the applicant with the one found in the
                # INI file. We use this to "correct" applications mistakes or
                # mistifications
                print(f'INFO: {self.fullname}: found override, setting {attr}={override}')
                setattr(self, attr, override)

    # this is to be used when we want to create a Person from a CSV file,
    # automatically loading unknown/unprocessed fields. Outside of testing
    # cases, most Person instances are created this way by grader
    @classmethod
    def from_row(cls, fields, values, relaxed=False, ini=None):
        # first instantiate a Person with the known/required fields
        #  - get the list of known fields
        known_fields = [item.name for item in dataclasses.fields(cls)]
        #  - set their values from those found in the CSV file
        hard_coded = {field:value for (field, value) in zip(fields, values)
                                  if field in known_fields}
        person = cls(**hard_coded, _relaxed=relaxed, _ini=ini)

        # add all the unknown/unprocessed fields
        # all these fields will be of type str
        for (field, value) in zip(fields, values):
            if field not in known_fields:
                setattr(person, field, value)

        return person

    def set_n_applied(self, archive):
        # set the number of previous applications (excluding the present one)
        # only works if an archive of previous applications, i.e. a list of
        # Applications objects is passed. This method is called during the initialization
        # of Grader
        if self._ini and \
                self._ini[f'n_applied_overrides.{self.fullname.lower()}'] is not None:
            # we don't count manually if an override was found
            return

        found = 0
        for year in archive:
            # try to find candidate by exact fullname
            candidates = year.filter(fullname=f'^{self.fullname}$')
            if not candidates:
                # they may write the name differently, let's try to match on the email
                # address
                candidates = year.filter(email=self.email)
            
            # We used to have a check here whether len(candidates) <= 1, but
            # in 2023, a person applied twice from different email addresses,
            # and we didn't notice that until a year later.
            if candidates:
                found += 1
            else:
                # We use fuzzy matching here, especially thought for people with
                # more then one first/last-name, who tend to skip some of their names
                # but they skip different ones every time.
                fuzzy_matches = year.fuzzy_fullname_filter(f'{self.fullname}')
                
                # Raise some warning if we find a potential match with 
                # partially the same name, we cannot be sure if it is a duplicate
                # The user has to manually write an override for this case based on the warning
                for p in fuzzy_matches:
                    print('\nWARNING: A partial (fuzzy) full name match found:\n'
                          f'\tApplicant name = {self.fullname} <{self.email}>\n'
                          f'\tPrevious name = {p.fullname} <{p.email}> from {year.ini.filename}\n'
                         )

        # self.applied must be a bool at this point, if not this method is been
        # called at the wrong time
        assert isinstance(self.applied, bool)

        if found and not self.applied:
            # inform the user that we are overriding the self.applied flag, given
            # that the applicant cearly forgot to do it themeselves
            print(f'INFO: {self.fullname}: n_applied={found}, setting applied=yes')
            self.applied = True
        if not found and self.applied:
            # Warn the user that someone claims to have applied even if we don't
            # find them: those cases must be analized manually and solved with
            # a n_applied override if necessary
            print('WARNING: person says they applied, but not found in archive: '
                  f'{self.fullname} <{self.email}>')
            self.applied = False

        self.n_applied = found

    # The score is expensive to compute, because it requires the
    # evaluation of the formula.
    def calculate_score(self, formula=None):
        if formula is None:
            if not self._ini:
                raise ValueError
            formula = self._ini.formula

        # create a key for the cache of score. We store there our own generation
        # (which is updated every time we change something on Person), the INI
        # file generation (which is updated every time something global changes
        # in the INI file, like for example some override was added or a reload
        # from disk was triggered, and finally the formula, which comes as a string
        if self._ini:
            key = (self._generation, self._ini.generation, formula)
            # we can return the cached score if nothing has changed
            if (v := self._score_cache.get(key, None)) is not None:
                return v

        # we must compute the score
        v = FormulaProxy(self).evaluate(formula)

        # store the score in cache and return it
        if self._ini:
            self._score_cache[key] = v

        return v

    @property
    def score(self):
        # str.format() can only access properties, not call functions on objects.
        # TODO: figure out if this is needed
        return self.calculate_score()


class FormulaProxy:
    # This object proxies formula evaluation for Person
    # It is useful because it knows how to translate text ratings into numeric
    # ratings as configured in the INI file, for example the entry
    #    [python_rating]
    #    competent = 1
    # would translate a mention of 'python' in the formula with '1' if the
    # corresponding Person hat python = 'Competent/Proficient'
    # In other words, this class is a mapping FormulaProxy.attr -> Person.attr (boring)
    # but more interestingly for FormulaProxy.attr_with_rating -> numerical value
    # corresponding to the string rating
    def __init__(self, person, overrides={}):
        # we keep a reference to Person
        self.person = person
        self.overrides = overrides

    def __getitem__(self, name):
        try:
            return self.overrides[name]
        except KeyError:
            pass

        if name == 'motivation':
            return self.person.motivation_scores.mean()
        # support returning not a number
        if name == 'nan':
            return math.nan

        # This may be a global field defined in the section 'formula' of the
        # INI file, like for example "location = Palermo".
        if (val := self.person._ini[f'formula.{name}']) is not None:
            return val

        try:
            return self.person.get_rating(name)
        except AttributeError:
            pass

        return getattr(self.person, name)

    def evaluate(self, formula):
        # evaluate the formula using ourselves as proxy
        return eval(formula, {}, self)
