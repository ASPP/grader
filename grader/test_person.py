from grader.person import Person

import pytest

MARCIN = dict(
    name = ' Jędrzej\t\t\tMarcin ',
    lastname = ' Mirosławski  Piołun ',
    email = ' marcin@example.com ',
    gender = 'other',
    institute = 'Instytut Pierwszy',
    group = 'Group',
    affiliation = 'Affilliation Affilliation Affilliation',
    position = 'Other',
    position_other = 'Whisperer',
    programming = 'Novice/Advanced Beginner',
    programming_description = 'Programming Description…',
    python = 'Competent/Proficient',
    vcs = 'git',
    open_source = 'User',
    open_source_description = 'Open Source Description…',
    cv = 'cv text is here\nline 2\nline3\n',
    motivation = 'motivation text is here\nline 2\nline3\n',
    born = '1980',
    nationality = 'Nicaragua',
    applied = 'No',
)

def test_person():
    p = Person(**MARCIN)

    assert p.name == 'Jędrzej Marcin'
    assert p.lastname == 'Mirosławski Piołun'
    assert p.fullname == 'Jędrzej Marcin Mirosławski Piołun'
    assert p.email == 'marcin@example.com'
    assert p.born == 1980
    assert isinstance(p.born, int)
    assert p.applied is False

    assert p.labels == []
    assert p.nonmale is True

def test_person_invalid_born():
    args = MARCIN | dict(born='1700')
    with pytest.raises(ValueError):
        p = Person(**args)

@pytest.mark.parametrize('field',
                         ['gender', 'programming', 'python', 'position'])
def test_person_invalid_field(field):
    args = MARCIN | dict(((field, 'cat'),))
    with pytest.raises(ValueError):
        p = Person(**args)

def test_person_attr_not_set():
    p = Person(**MARCIN)

    with pytest.raises(AttributeError):
        p.attr_not_set

def test_person_unknown_field():
    args = MARCIN | dict(unkwown_field='123')
    with pytest.raises(TypeError):
        p = Person(**args)
