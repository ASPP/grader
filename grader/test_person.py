from grader.person import Person
from grader.applications_ import ApplicationsIni

import pytest

from .test_applications_ import get_ini

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

def test_person_with_ini(tmp_path):
    ini = get_ini(tmp_path)
    
    p = Person(**MARCIN, _ini=ini)

    assert p.motivation_scores == [1, None]

    p.set_motivation_score(0, identity='other')
    assert p.motivation_scores == [1, 0]
    assert ini.data['motivation_score-other'][p.fullname.lower()] == 0

    assert p.labels == ['UTF-8', 'VEGAN']
    p.add_label('PALEO')
    assert p.labels == ['PALEO', 'UTF-8', 'VEGAN']

    # test that we don't add the label again
    p.add_label('PALEO')
    assert p.labels == ['PALEO', 'UTF-8', 'VEGAN']

    p.remove_label('UTF-8')
    assert p.labels == ['PALEO', 'VEGAN']

    p.remove_label('VEGAN')
    assert p.labels == ['PALEO']

    p.remove_label('PALEO')
    assert p.labels == []

    p.remove_label('PALEO')
    assert p.labels == []

def test_person_not_in_ini(tmp_path):
    ini = get_ini(tmp_path)

    args = MARCIN | dict(name='Name', lastname='Unset')
    p = Person(**args, _ini=ini)

    assert p.motivation_scores == [None, None]

    p.set_motivation_score(0, identity='other')
    assert p.motivation_scores == [None, 0]
    assert ini.data['motivation_score-other'][p.fullname.lower()] == 0

    assert p.labels == []
    p.add_label('PALEO')
    assert p.labels == ['PALEO']

    out = tmp_path / 'ini1.copy'
    ini.save(out)

    ini = ApplicationsIni(out)

    args = MARCIN | dict(name='Name', lastname='Unset')
    p = Person(**args, _ini=ini)

    assert p.motivation_scores == [None, 0]
    assert p.labels == ['PALEO']
    assert p.fullname.lower() in ini.data['labels']

    p.remove_label('PALEO')
    assert p.labels == []
    assert p.fullname.lower() not in ini.data['labels']

    out = tmp_path / 'ini1.copy'
    ini.save(out)

    # check that we don't an empty key assignment in [labels]
    assert 'name unset =\n' not in out.read_text()
