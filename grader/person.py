import dataclasses
from functools import cached_property
import datetime

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
    affiliation: str
    position: str
    position_other: str    # non-empty if position=='Other'
    programming: str
    programming_description: str
    python: str
    vcs: str
    open_source: str
    open_source_description: str
    cv: str
    motivation: str
    born: int
    nationality: str
    applied: bool

    labels : [str] = dataclasses.field(default_factory=list)

    @cached_property
    def fullname(self) -> str:
            return f'{self.name} {self.lastname}'

    @cached_property
    def nonmale(self) -> str:
            return self.gender.lower() != 'male'

    def __post_init__(self):
        # strip extraneous whitespace from around and within the name
        self.name = ' '.join(self.name.split())
        self.lastname = ' '.join(self.lastname.split())
        self.email = self.email.strip()

        self.born = int(self.born)
        if not (1900 < self.born < _year_now):
            raise ValueError(f'Bad birth year {self.born}')

        self.applied = self.applied[0] not in 'nN'

        for field in ('gender', 'programming', 'python', 'position'):
            value = getattr(self, field).lower()
            if value not in globals()[f'VALID_{field.upper()}']:
                raise ValueError(f'Bad {field} value: {value}')

    @classmethod
    def new(cls, fields, values):
        known_fields = [item.name for item in dataclasses.fields(cls)]
        parta = {field:value for (field, value) in zip(fields, values)
                 if field in known_fields}
        person = cls(**parta)

        for (field, value) in zip(fields, values):
            if field not in known_fields:
                setattr(person, field, value)

        return person
