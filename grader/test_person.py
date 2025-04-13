import math
import time

from grader.person import (convert_bool, Person, FormulaProxy)
from grader.applications import ApplicationsIni, Applications

import pytest
import numpy as np
import math

import csv

from .test_applications import get_ini

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

# This one is used to test for repeated people
JOSE = dict(
    name = ' Jose Javier Edmundo ',
    lastname = ' Garcia Lopez ',
    email = ' j.garcia@example.com ',
    gender = 'other',
    institute = 'Real escuela de Caracas',
    group = 'Group',
    affiliation = 'Departamento de astrologia',
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

def test_convert_bool():
    assert convert_bool('y') is True
    assert convert_bool('Yes') is True
    assert convert_bool('NO') is False
    assert convert_bool('false') is False
    assert convert_bool('True') is True
    assert convert_bool(0) is False
    assert convert_bool(1) is True
    with pytest.raises(ValueError):
        convert_bool(0.0)
    with pytest.raises(ValueError):
        convert_bool('Ciao')

def test_person():
    p = Person(**MARCIN)

    assert p.name == 'Jędrzej Marcin'
    assert p.lastname == 'Mirosławski Piołun'
    assert p.fullname == 'Jędrzej Marcin Mirosławski Piołun'
    assert p.email == 'marcin@example.com'
    assert p.born == 1980
    assert isinstance(p.born, int)
    assert p.applied is False
    assert p.n_applied == 0

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

def test_person_applied():
    args = MARCIN | dict(applied='Yes')
    p = Person(**args)

    assert p.applied is True
    assert p.n_applied == 0


def test_person_without_ini():
    p = Person(**MARCIN)

    assert p.motivation_scores == []
    assert math.isnan(p.get_motivation_score(0))

    with pytest.raises(ValueError):
        # We don't know the formula without the ini
        p.calculate_score()

    assert math.isnan(p.calculate_score('motivation'))

    with pytest.raises(ValueError):
        p.set_motivation_score(0, 0)

    with pytest.raises(ValueError):
        p.add_label('VEGAN')

    with pytest.raises(ValueError):
        p.remove_label('VEGAN')


def test_person_with_ini(tmp_path):
    ini = get_ini(tmp_path)

    p = Person(**MARCIN, _ini=ini)

    assert p.motivation_scores == [1, None]

    p.set_motivation_score(0, identity='other')
    assert p.get_motivation_score('other') == 0
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

ini_extra = '''\
[formula]
formula = (nationality!=affiliation)*0.4 + programming*0.2 + cooking*0.2 + nonmale*0.2 + (nationality!=location)*0.1
location = Nicaragua

[cooking_rating]
paleo = -1.0
vegan = 2.0

[programming_rating]
competent = 1.0
expert = 0.0
novice = 0.0

[n_applied_overrides]
jędrzej marcin mirosławski piołun = 3
'''

def test_formula_proxy(tmp_path):

    ini = get_ini(tmp_path, ini_extra)

    p = Person(**MARCIN, _ini=ini)
    p.cooking = 'paleo'

    f = FormulaProxy(p)

    assert f['gender'] == 'other'
    assert f['nonmale'] == 1
    assert np.isnan(f['nan'])
    assert f['programming'] == 0.0
    assert f['cooking'] == -1
    assert f['location'] == 'Nicaragua'

def test_person_score(tmp_path):
    ini = get_ini(tmp_path, ini_extra)
    p = Person(**MARCIN, _ini=ini)

    assert len(p._score_cache) == 0

    p.cooking = 'paleo'
    score = p.score
    assert score == 0.4 + 0 + -1.0*0.2 + 0.2 + 0
    assert len(p._score_cache) == 1

    assert p.score == score
    assert len(p._score_cache) == 1

    p.cooking = 'vegan'
    score = p.score
    assert score == 0.4 + 0 + 2.0*0.2 + 0.2 + 0
    assert len(p._score_cache) == 2

    assert p.score == score
    assert len(p._score_cache) == 2

    # manually tweak the cache to test that we're getting the value from the cache
    for key in p._score_cache:
        p._score_cache[key] = 100

    assert p.score == 100

    # invalidate the cache by setting an attribute
    p.cooking = 'paleo'
    assert p.score == 0.4 + 0 + -1.0*0.2 + 0.2 + 0

    # set attribute on the ini, check if cache is invalidated
    ini['formula.location'] = 'Poland'
    assert p.score == 0.4 + 0 + -1.0*0.2 + 0.2 + 1*0.1

    p.gender = 'male'
    assert p.nonmale is False
    assert p.score == 0.4 + 0 + -1.0*0.2 + 0*0.2 + 1*0.1

def test_person_ini_reload(tmp_path):
    ini = get_ini(tmp_path, ini_extra)
    p = Person(**MARCIN, _ini=ini)

    assert p.labels == ['UTF-8', 'VEGAN']

    time.sleep(0.01)
    ini.filename.write_text(ini.filename.read_text().replace('UTF-8', 'ASCII'))

    assert ini.reload_if_modified() == True

    assert p.labels == ['ASCII', 'VEGAN']

def test_set_n_applied_override(tmp_path):
    ini = get_ini(tmp_path, ini_extra)
    p = Person(**MARCIN, _ini=ini)

    assert p.n_applied == 3
    p.set_n_applied({2020 : None})
    assert p.n_applied == 3

def test_get_rating(tmp_path):
    ini = get_ini(tmp_path, ini_extra)
    p = Person(**MARCIN, _ini=ini)

    # These attributes exist in the Person dataclass, and their rating exist in the INI file
    assert p.get_rating("programming") == 0
    p.cooking = 'paleo'
    assert p.get_rating("cooking") == -1

    # These attribute exists in the Person dataclass, its rating exist in the INI file, but the given key is not rated
    p.cooking = 'cimbalese'
    with pytest.raises(KeyError):
        p.get_rating("cooking")

    # The skiing attribute does not exist in the Person dataclass
    with pytest.raises(AttributeError):
        p.get_rating("skiing")


# Testing repeated people
def test_repeated_people(tmp_path, capfd):
    ini_file = 'just_jose.ini'
    ini = get_ini(tmp_path, ini_filename=ini_file)
    ini_path = tmp_path / ini_file

    # Create temporary application csv files
    my_dict = JOSE
    filepath = tmp_path / 'JOSE.csv'
    with open(filepath, 'w', encoding="utf-8") as f:
        w = csv.DictWriter(f, my_dict.keys())
        w.writeheader()
        w.writerow(my_dict)

    # Re-load as applications instance
    # This avoids having to re-write the Applications init, which usually expects a csv    
    archive = [Applications(filepath, ini_file=ini_path)]

    # Test two different people
    p = Person(**MARCIN, _ini=ini)
    p.set_n_applied(archive)
    assert p.n_applied == 0

    # Case where the person says they applied but they did not
    MARCIN_copy = MARCIN.copy()
    MARCIN_copy['applied'] = 'yes'
    p = Person(**MARCIN_copy, _ini=ini)
    p.set_n_applied(archive)
    assert p.n_applied == 0
    out, err = capfd.readouterr()
    assert 'WARNING: person says they applied' in out

    # Test against itself, should find the matching fullname
    p = Person(**JOSE, _ini=ini)
    p.set_n_applied(archive)
    assert p.n_applied == 1
    out, err = capfd.readouterr()
    assert 'setting applied=yes' in out

    # In this copy the name is not the same, 
    # so the email should lead to finding the duplicate
    JOSE1 = JOSE.copy()
    JOSE1['name'] = 'Jose'
    p = Person(**JOSE1, _ini=ini)
    p.set_n_applied(archive)
    assert p.n_applied == 1
    
    # Here neither the fullname nor the email is the exact same
    # But fuzzy name comparison should print a warning
    JOSE2 = JOSE1.copy()
    JOSE2['email'] = 'joselito@proton.fake'
    p = Person(**JOSE2, _ini=ini)
    p.set_n_applied(archive)
    # Even if the fuzzy match is found do not assume it is correct
    assert p.n_applied == 0
    # Check if the fuzzy warning was printed
    out, err = capfd.readouterr()
    assert 'WARNING: A partial (fuzzy)' in out
