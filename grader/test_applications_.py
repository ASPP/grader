import pathlib
import os

import grader.applications_

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
    grader.applications_.load(path, relaxed=relaxed)

def test_applications_ini():
    import pprint
    inifile = '/home/tiziano/git/pythonschool/applications/grader.conf'
    ini = grader.applications_.ApplicationsIni(inifile)
    pprint.pprint(ini.data, sort_dicts=False)
    ini.data['groups_programming_rating']['project'] = 10.0
    ini.save()
