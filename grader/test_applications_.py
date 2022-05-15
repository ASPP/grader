import pathlib
import os
from io import StringIO

from grader.applications_ import (load, ApplicationsIni)

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
    load(path, relaxed=relaxed)


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

[labels]
john doe = VEGAN, VIP

"""

def test_applications_ini_read(tmp_path):
    input = tmp_path / 'ini0.ini'
    input.write_text(ini_string)

    ini = ApplicationsIni(input)
    assert ini['extra.key_str'] == 'value'
    assert ini['extra.key_num'] == '111.5'
    with pytest.raises(KeyError):
        ini['extra.missing']

    assert ini['cooking_rating.key'] == 5.0

    assert ini['motivation_score-zbyszek.person one'] == 1
    assert ini['motivation_score-zbyszek.person two'] == -1
    assert ini['motivation_score-zbyszek.person three'] == 0
    assert ini['motivation_score-zbyszek.some son jr.'] == -1

    assert ini['labels.john doe'] == 'VEGAN VIP'.split()

def test_applications_ini_save(tmp_path):
    input = tmp_path / 'ini1.ini'
    input.write_text(ini_string)

    ini = ApplicationsIni(input)

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
