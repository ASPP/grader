import pathlib
import os
from io import StringIO

from grader.applications_ import (
    load_applications_csv,
    ApplicationsIni,
    Applications)

import pytest

APPLICATIONS_ROOT = (os.getenv('APPLICATIONS_ROOT') or
                     '/home/zbyszek/pythonschool/pythonschool/')

APPLICATIONS = pathlib.Path(APPLICATIONS_ROOT).glob('**/applications.csv')
APPLICATIONS_ORIGINAL = list(pathlib.Path(APPLICATIONS_ROOT).glob('**/applications_original.csv'))
APPLICATIONS = sorted(APPLICATIONS_ORIGINAL +
                      [p for p in APPLICATIONS
                       if p.with_name('applications_original.csv') not in APPLICATIONS_ORIGINAL], reverse=True)

@pytest.mark.parametrize('path', APPLICATIONS)
def test_all_years(path):
    # years before 2012 are to be treated less strictly
    relaxed = any(f'{year}-' in str(path) for year in range(2009,2012))
    load_applications_csv(path, relaxed=relaxed)

# FIXME: make identities sorted alphabetically

ini_string = """\
[extra]
key_str = value
key_num = 111.5

[cooking_rating]
key = 5.0

[motivation_score-zbyszek]
person one = 1
person two = -1
person three = 0
some son jr. = -1
jędrzej marcin mirosławski piołun = 1

[motivation_score-other]
person one = -1
person two = 1
some son jr. = 1

[labels]
john doe = VEGAN, VIP
jędrzej marcin mirosławski piołun = UTF-8, VEGAN
person one = PALEO

"""

def get_ini(tmp_path):
    input = tmp_path / 'ini1.ini'
    input.write_text(ini_string)
    return ApplicationsIni(input)

def get_applications_csv(tmp_path):
    from .test_person import MARCIN

    person_one = MARCIN | dict(
        name = 'Person',
        lastname = 'One',
        affiliation = 'Paleolithic 1')

    person_two = MARCIN | dict(
        name = 'Person',
        lastname = 'Two',
        affiliation = 'Completely Modern 1')

    csv = '\n'.join((';'.join(f'"{key}"' for key in MARCIN.keys()),
                     ';'.join(f'"{val}"' for val in MARCIN.values()),
                     ';'.join(f'"{val}"' for val in person_one.values()),
                     ';'.join(f'"{val}"' for val in person_two.values()),
                     ))

    input = tmp_path / 'applications.csv'
    input.write_text(csv)

    return input

def test_applications_ini_read(tmp_path):
    ini = get_ini(tmp_path)

    assert ini['extra.key_str'] == 'value'
    assert ini['extra.key_num'] == '111.5'
    with pytest.raises(KeyError):
        ini['extra.missing']

    assert ini['cooking_rating.key'] == 5.0

    assert ini['motivation_score-zbyszek.person one'] == 1
    assert ini['motivation_score-zbyszek.person two'] == -1
    assert ini['motivation_score-zbyszek.person three'] == 0
    assert ini['motivation_score-zbyszek.some son jr.'] == -1

    assert ini['motivation_score-other.person one'] == -1
    assert ini['motivation_score-other.person two'] == 1
    assert ini['motivation_score-other.person three'] == None
    assert ini['motivation_score-other.some son jr.'] == 1

    assert ini['labels.john doe'] == 'VEGAN VIP'.split()

    assert ini.get_motivation_scores('Person One') == [1, -1]
    assert ini.get_motivation_scores('PERSON TWO') == [-1, 1]
    assert ini.get_motivation_scores('person three') == [0, None]
    assert ini.get_motivation_scores('Some Son Jr.') == [-1, 1]

    assert ini.get_motivation_scores('Unknown Person') == [None, None]

def test_applications_ini_file_missing(tmp_path):
    ini = ApplicationsIni(tmp_path / 'missing.ini')

    assert ini.get_motivation_score('Person One', identity='other') == None
    
    ini.set_motivation_score('Person One', 2, identity='other')
    assert ini.get_motivation_score('Person One', identity='other') == 2

    assert not ini.filename.exists()

    ini.save()
    assert ini.filename.exists()

def test_applications_ini_read(tmp_path):
    ini = get_ini(tmp_path)

    assert ini.get_motivation_score('Person One', identity='other') == -1
    
    ini.set_motivation_score('Person One', 2, identity='other')
    assert ini.get_motivation_score('Person One', identity='other') == 2
    
def test_applications_ini_save(tmp_path):
    ini = get_ini(tmp_path)

    out = tmp_path / 'ini1.copy'
    ini.save(out)

    assert out.read_text() == ini_string

    # Replace an exisiting entry.
    # We use an int, but the type is converted to float internally
    # so we get '6.0' when reading the data back again.
    ini['cooking_rating.key'] = 6
    ini.save(out)
    assert '[cooking_rating]\nkey = 6.0\n' in out.read_text()

    # Add a key to an exisiting section
    ini['cooking_rating.some_long_key'] = 7
    ini.save(out)
    assert '\nsome_long_key = 7.0\n' in out.read_text()

    ini2 = ApplicationsIni(out)
    assert ini2['cooking_rating.some_long_key'] == 7.0

def test_applications_object(tmp_path):
    csv = get_applications_csv(tmp_path)
    ini = get_ini(tmp_path).filename

    app = Applications(csv, ini)

    assert len(app) == 3
    assert len(app.people) == 3
    assert app.ini.filename == ini

    vegans = app.filter(label = ['VEGAN'])
    assert len(vegans) == 1
    vegans.name == ['Jędrzej Marcin']

    vegans = app.filter(label = 'VEGAN')
    assert len(vegans) == 1
    vegans.name == ['Jędrzej Marcin']

    vegans = app.filter(label = ['VEGAN', 'UTF-8'])
    assert len(vegans) == 1
    vegans.name == ['Jędrzej Marcin']

    byname = app.filter(name = 'Person')
    assert len(byname) == 2
    byname.name == ['Person', 'Person']
    byname.lastname = ['One', 'Two']

    byname = app.filter(name = 'Person', affiliation='Paleolithic 1')
    assert len(byname) == 1
    byname.fullname == ['Person One']

    byname = app.filter(name = 'Person', affiliation=r'Paleolithic')
    assert len(byname) == 1
    byname.fullname == ['Person One']

    byname = app.filter(name = 'Person', affiliation=r'paleo[a-z]ithic')
    assert len(byname) == 1
    byname.fullname == ['Person One']

    byname = app.filter(name = 'Person', affiliation=r'^aleolithic')
    assert len(byname) == 0
    byname.fullname == []

    # also check with utf-8 in the pattern and label/non-label matching
    byname = app.filter(label = ['VEGAN', 'UTF-8'], name = 'Jędrzej')
    assert len(byname) == 1
    byname.name == ['Jędrzej Marcin']

    with pytest.raises(AttributeError):
        app.filter(unknown_attr = '11')
