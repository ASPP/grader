import dataclasses
from functools import cached_property
import datetime

# List of valid values for fields in the Person object
# The values need to match with what is used in the application form

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

    labels : [str] = dataclasses.field(default_factory=list)

    # internal attribute signaling relaxed checking
    # needed to relax value checks for old application files [should not be
    # necessary for new application files
    _relaxed: bool = dataclasses.field(default=False, repr=False)

    @cached_property
    def fullname(self) -> str:
            return f'{self.name} {self.lastname}'

    @cached_property
    def nonmale(self) -> str:
            return self.gender.lower() != 'male'

    def __post_init__(self):
        # strip extraneous whitespace from around and within names and emails
        self.name = ' '.join(self.name.split())
        self.lastname = ' '.join(self.lastname.split())
        self.email = self.email.strip()
        # the birth year must be an integer
        self.born = int(self.born)
        # transform applied to a boolean
        self.applied = self.applied[0] not in 'nN'

        # only run the checks if we are in strict mode
        if self._relaxed:
            return

        if not (1900 <= self.born <= _year_now):
            raise ValueError(f'Bad birth year {self.born}')

        for field in ('gender', 'programming', 'python', 'position'):
            value = getattr(self, field).lower()
            if value not in globals()[f'VALID_{field.upper()}']:
                raise ValueError(f'Bad {field} value: {value}')

    # this is to be used when we want to create a Person from a CSV file,
    # automatically loading unknown/unprocessed fields
    @classmethod
    def new(cls, fields, values, relaxed=False):
        # first instantiate a Person with the known/required fields
        known_fields = [item.name for item in dataclasses.fields(cls)]
        hard_coded = {field:value for (field, value) in zip(fields, values)
                                  if field in known_fields}
        person = cls(**hard_coded, _relaxed=relaxed)

        # add all the unknown/unprocessed fields
        for (field, value) in zip(fields, values):
            if field not in known_fields:
                setattr(person, field, value)

        return person
