from .grader import Grader

import pytest

CSV_APPLICATIONS = """
"First name","Last name","Nationality","Affiliation","programming","open_source","applied","python","born","gender","email","group","institute","vcs","underrep","position","position_other","programming_description","open_source_description","cv","motivation"
"John","Doe","Italy","Italy","expert","user","No","expert","1978","Male","john.doe@gmail.com","Group A","Institute A","yes","no","PhD student","","competent/proficient","I like it","(2001) Trip around the world","Very high"
"Mary Jane","Smith","Germany","UK","competent/proficient","minor contributions","No","competent/proficient","1999","Female","mary99@gmail.com","Group B","Institute B","no","yes","post-doctorate","","novice/advanced beginner","blah","(2020) Chilling","Not interested"
""".strip()


CONF = """
[formula]
formula = (nationality!=affiliation)
accept_count = 30

[programming_rating]
competent = 1.0
expert = 0.0
novice = 0.0

[open_source_rating]
never used = 0.0
minor contributions = 0.5
major contributions = 1.0
user = 0.3
project membership = 1.0
minor contributions (bug reports, mailing lists, ...) = 0.5

[python_rating]
competent = 1.0
none = 0.0
expert = 0.5
novice = 0.5

[vcs_rating]
yes = 1.0
no = 0.0

[underrep_rating]
yes = 1.0
no = 0.0

[labels]
john doe = RICH
mary jane smith = POOR

[fields]
name = First name
lastname = Last name
nationality = Nationality
affiliation = Affiliation
programming = programming
open_source = open_source
applied = applied
python = python
born = born
gender = gender
email = email
group = group
institute = institute
vcs = vcs
underrep = underrep

[equivs]

[motivation_score-zbyszek]

[motivation_score-rike]
"""


def _tmp_application_files(tmp_path, config_string, csv_string):
    config_tmp_path = tmp_path / 'applications.ini'
    config_tmp_path.write_text(config_string)
    csv_tmp_path = tmp_path / 'applications.csv'
    csv_tmp_path.write_text(csv_string)
    return config_tmp_path, csv_tmp_path


def test_grader_identity(tmp_path, capsys):
    config_tmp_path, csv_tmp_path = _tmp_application_files(tmp_path, CONF, CSV_APPLICATIONS)

    grader = Grader(identity='zbyszek', csv_file=csv_tmp_path)
    assert grader.identity == 'zbyszek'

    grader.do_identity('  rike  ')
    assert grader.identity == 'rike'

    out, err = capsys.readouterr()
    assert err == ''
    assert 'Identity set to rike' in out

def test_grader_bad_identity(tmp_path, capsys):
    config_tmp_path, csv_tmp_path = _tmp_application_files(tmp_path, CONF, CSV_APPLICATIONS)

    grader = Grader(csv_file=csv_tmp_path)

    assert grader.identity is None

    with pytest.raises(ValueError):
        grader.do_identity('  bad  ')
    assert grader.identity is None

    out, err = capsys.readouterr()
    assert err == ''
    assert 'Identity set to bad' not in out


def test_grader_formula_display(tmp_path, capsys):
    config_tmp_path, csv_tmp_path = _tmp_application_files(tmp_path, CONF, CSV_APPLICATIONS)

    grader = Grader(csv_file=csv_tmp_path)

    assert grader.applications.ini.formula == '(nationality!=affiliation)'

    grader.do_formula('')

    assert grader.applications.ini.formula == '(nationality!=affiliation)'

    out, err = capsys.readouterr()
    assert err == ''
    assert '(nationality!=affiliation)' in out


def test_grader_formula_setting(tmp_path, capsys):
    config_tmp_path, csv_tmp_path = _tmp_application_files(tmp_path, CONF, CSV_APPLICATIONS)

    grader = Grader(csv_file=csv_tmp_path)

    assert grader.applications.ini.formula == '(nationality!=affiliation)'

    grader.do_formula('  (nationality==affiliation) + 2  ')

    assert grader.applications.ini.formula == '(nationality==affiliation) + 2'

    out, err = capsys.readouterr()
    assert err == ''
    assert '(nationality==affiliation) + 2' in out


def test_grader_rank(tmp_path, capsys):
    # Basic test, just checking that it does not crash
    config_tmp_path, csv_tmp_path = _tmp_application_files(tmp_path, CONF, CSV_APPLICATIONS)

    grader = Grader(identity=1, csv_file=csv_tmp_path)
    grader.do_rank(args='')

    out, err = capsys.readouterr()
    output_lines = out.replace('-', '').strip().split('\n')[-2:]
    # Mary Jane is first because John's nationality is the same
    # as his affiliation
    assert 'Mary Jane' in output_lines[0]
    assert 'John Doe' in output_lines[1]


def test_grader_rank_labels_filter(tmp_path, capsys):
    # Basic test, just checking that it down not crash
    config_tmp_path, csv_tmp_path = _tmp_application_files(tmp_path, CONF, CSV_APPLICATIONS)

    grader = Grader(identity=1, csv_file=csv_tmp_path)
    grader.do_rank(args='-l RICH')

    out, err = capsys.readouterr()
    output_lines = out.replace('-', '').strip().split('\n')[-1:]
    assert 'John Doe' in output_lines[0]
