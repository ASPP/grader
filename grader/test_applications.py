import pathlib
import os
import time

from grader.applications import (
    load_applications_csv,
    ApplicationsIni,
    Applications)

import pytest

APPLICATIONS_ROOT = (os.getenv('APPLICATIONS_ROOT') or
                     os.path.expanduser('~/pythonschool/pythonschool/'))

EXTRA_APPLICATIONS = sorted(
    pathlib.Path(APPLICATIONS_ROOT).glob('**/applications.csv'),
    reverse=True)

BUILTIN_APPLICATIONS = (
    'tests/data/year99/applications.csv',
)
BUILTIN_APPLICATIONS = (pathlib.Path(p) for p in BUILTIN_APPLICATIONS)

APPLICATIONS = (*EXTRA_APPLICATIONS, *BUILTIN_APPLICATIONS)

@pytest.mark.parametrize('path', APPLICATIONS,
                         ids=(lambda path: path.parent.name))
def test_all_years(path):
    # years before 2012 are to be treated less strictly
    relaxed = any(f'{year}-' in str(path) for year in range(2009,2012))
    load_applications_csv(path, relaxed=relaxed)

# FIXME: make identities sorted alphabetically

ini_string = """\
[extra]
key_str = value
key_num = 111.5

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

[verify_rating_is_unsorted_rating]
novice = +10.0
competent = 0.0
expert = -10.0

[labels]
john doe = VEGAN, VIP
jędrzej marcin mirosławski piołun = UTF-8, VEGAN
person one = PALEO

"""

ini_sorted = """\
[extra]
key_num = 111.5
key_str = value

[motivation_score-zbyszek]
jędrzej marcin mirosławski piołun = 1
person one = 1
person three = 0
person two = -1
some son jr. = -1

[motivation_score-other]
person one = -1
person two = 1
some son jr. = 1

[verify_rating_is_unsorted_rating]
novice = 10.0
competent = 0.0
expert = -10.0

[labels]
jędrzej marcin mirosławski piołun = UTF-8, VEGAN
john doe = VEGAN, VIP
person one = PALEO

"""


def get_ini(tmp_path, *extra, ini_filename='ini1.ini'):
    input = tmp_path / ini_filename
    input.write_text(ini_string + '\n'.join(extra))

    return ApplicationsIni(input)

def get_applications_csv(tmp_path):
    from .test_person import MARCIN

    person_one = MARCIN | dict(
        name = 'Person',
        lastname = 'One',
        affiliation = 'Paleolithic 1',
        born=1981)

    person_two = MARCIN | dict(
        name = 'Person',
        lastname = 'Two',
        affiliation = 'Completely Modern 1',
        born=1982)

    csv = '\n'.join((';'.join(f'"{key}"' for key in MARCIN.keys()),
                     ';'.join(f'"{val}"' for val in MARCIN.values()),
                     ';'.join(f'"{val}"' for val in person_one.values()),
                     ';'.join(f'"{val}"' for val in person_two.values()),
                     ))

    input = tmp_path / 'applications.csv'
    input.write_text(csv)

    return input

@pytest.fixture
def app(tmp_path):
    csv = get_applications_csv(tmp_path)
    ini = get_ini(tmp_path).filename
    return Applications(csv, ini)

def test_applications_ini_read(tmp_path):
    ini = get_ini(tmp_path)

    assert ini['extra.key_str'] == 'value'
    assert ini['extra.key_num'] == '111.5'
    assert ini['extra.missing'] == None

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

def test_applications_ini_reload(tmp_path):
    ini = get_ini(tmp_path)

    assert ini.reload_if_modified() == False

    # we need to sleep a bit because the can be fast enough to do the
    # modification within the granularity of the file system timestamp
    time.sleep(0.01)
    ini.filename.touch()
    assert ini.reload_if_modified() == True

    assert ini.reload_if_modified() == False

    time.sleep(0.01)
    with ini.filename.open('a') as f:
        f.write('[cleaning]\nvacuum = 3\n')
    assert ini.reload_if_modified() == True
    assert ini['cleaning.vacuum'] == '3'

def test_applications_ini_file_missing(tmp_path):
    ini = ApplicationsIni(tmp_path / 'missing.ini')

    assert ini.get_motivation_score('Person One', identity='other') == None

    ini.set_motivation_score('Person One', 2, identity='other')
    assert ini.get_motivation_score('Person One', identity='other') == 2

    assert not ini.filename.exists()

    ini.save()
    assert ini.filename.exists()

def test_applications_ini_scores(tmp_path):
    ini = get_ini(tmp_path)

    assert ini.get_motivation_score('Person One', identity='other') == -1

    ini.set_motivation_score('Person One', 2, identity='other')
    assert ini.get_motivation_score('Person One', identity='other') == 2

def test_applications_ini_save(tmp_path):
    ini = get_ini(tmp_path)

    out = tmp_path / 'ini1.copy'
    ini.save(out)

    assert out.read_text() == ini_sorted

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

def test_applications_object(app):
    assert len(app) == 3
    assert len(app.people) == 3

    alls = app.filter()
    assert len(alls) == 3

    vegans = app.filter(label = ['VEGAN'])
    assert len(vegans) == 1
    assert vegans.name == ['Jędrzej Marcin']

    vegans = app.filter(label = 'VEGAN')
    assert len(vegans) == 1
    assert vegans.name == ['Jędrzej Marcin']

    vegans = app.filter(label = ['VEGAN', 'UTF-8'])
    assert len(vegans) == 1
    assert vegans.name == ['Jędrzej Marcin']

    byname = app.filter(name = 'Person')
    assert len(byname) == 2
    assert byname.name == ['Person', 'Person']
    assert byname.lastname == ['One', 'Two']

    byname_and_l = app.filter(name = 'Person', label=['-','PALEO'])
    assert len(byname_and_l) == 1
    assert byname_and_l.name == ['Person']
    assert byname_and_l.lastname == ['Two']

    byname = app.filter(name = 'Person', affiliation='Paleolithic 1')
    assert len(byname) == 1
    assert byname.fullname == ['Person One']

    byname = app.filter(name = 'Person', affiliation=r'Paleolithic')
    assert len(byname) == 1
    assert byname.fullname == ['Person One']

    byname = app.filter(name = 'Person', affiliation=r'paleo[a-z]ithic')
    assert len(byname) == 1
    assert byname.fullname == ['Person One']

    byname = app.filter(name = 'Person', affiliation=r'^aleolithic')
    assert len(byname) == 0
    assert byname.fullname == []

    # also check with utf-8 in the pattern and label/non-label matching
    byname = app.filter(label = ['VEGAN', 'UTF-8'], name = 'Jędrzej')
    assert len(byname) == 1
    assert byname.name == ['Jędrzej Marcin']

    with pytest.raises(AttributeError):
        app.filter(unknown_attr = '11')

    # non-string match
    byyear = app.filter(born=1980)
    assert len(byyear) == 1
    assert byyear.name == ['Jędrzej Marcin']

    # TODO: this should fail:
    # byname.lastname = ['One', 'Two']

    fullname = app.filter(fullname = 'Person One')
    assert len(fullname) == 1
    assert fullname.fullname == ['Person One']

def test_applications_getitem(app):
    assert len(app) == 3
    assert app['Person One'].fullname == 'Person One'
    assert app['person one'].fullname == 'Person One'
    assert app[1].fullname == 'Person One'
    with pytest.raises(TypeError):
        app[3.0]
    with pytest.raises(IndexError):
        app['Unkown Person']

def test_applications_labels(app):
    assert app['Person One'].add_label('VIP') is True
    assert app['Person One'].labels == ['PALEO', 'VIP']

    assert app['Person One'].add_label('VIP') is False
    assert app['Person One'].labels == ['PALEO', 'VIP']

    assert app['Person One'].add_label('VEGAN') is True
    assert app['Person One'].labels == ['PALEO', 'VEGAN', 'VIP']

    assert app['Person One'].add_label('VIRULENT') is True
    assert app['Person One'].labels == ['PALEO', 'VEGAN', 'VIP', 'VIRULENT']

    assert app['Person One'].add_label('VIRULENT') is False
    assert app['Person One'].labels == ['PALEO', 'VEGAN', 'VIP', 'VIRULENT']

    assert app['Person Two'].labels == []

    assert app['Person One'].remove_label('VIP') is True
    assert app['Person One'].labels == ['PALEO', 'VEGAN', 'VIRULENT']

    assert app['Person One'].remove_label('VIP') is False
    assert app['Person One'].labels == ['PALEO', 'VEGAN', 'VIRULENT']

    assert app['Person One'].remove_label('VEGAN') is True
    assert app['Person One'].labels == ['PALEO', 'VIRULENT']

    assert app['Person One'].remove_label('VIRULENT') is True
    assert app['Person One'].labels == ['PALEO']

    assert app['Person One'].remove_label('VIRULENT') is False
    assert app['Person One'].labels == ['PALEO']

    assert app['Person One'].remove_label('PALEO') is True
    assert app['Person One'].labels == []

    text = app.ini.to_string()

    assert 'john doe = VEGAN, VIP' in text
    assert 'jędrzej marcin mirosławski piołun = UTF-8, VEGAN' in text

def test_applications_all_labels(app):
    assert app.all_labels() == {'PALEO', 'UTF-8', 'VEGAN'}
    assert app['Person One'].add_label('VIRULENT') is True
    assert app.all_labels() == {'PALEO', 'UTF-8', 'VEGAN', 'VIRULENT'}

def test_applications_item_access(app):
    assert len(app) == 3
    assert app['Person One'].fullname == 'Person One'
    assert app[1].fullname == 'Person One'
    with pytest.raises(TypeError):
        assert app[1.0]
