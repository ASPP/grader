from .grader import Grader
from .util import our_configfile


CSV_APPLICATIONS = """
"First name","Last name","Nationality","Affiliation","programming","open_source","applied","python","born","gender","email","group","institute"
"John","Doe","Italy","Italy","competent","user","No","competent","1978","Male","john.doe@gmail.com","Group A","Institute A"
"Mary Jane","Smith","Germany","UK","expert","minor contributions","No","competent","1999","Female","mary99@gmail.com","Group B","Institute B"
""".strip()


CONF = """
[formula]
formula = (nationality!=affiliation)

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

[labels]
john doe = RICH
mary jane smith = POOR
"""


def _tmp_application_files(tmpdir, config_string, csv_string):
    config_tmpfile = tmpdir.join('test_grader.conf')
    config_tmpfile.write(config_string)
    csv_tmpfile = tmpdir.join('test_applications.csv')
    csv_tmpfile.write(csv_string)
    return config_tmpfile, csv_tmpfile


def test_grader_init(tmpdir):
    # Basic test, just checking that it down not crash
    config_string = ''
    config_tmpfile, csv_tmpfile = _tmp_application_files(
        tmpdir, config_string, CSV_APPLICATIONS)
    config = our_configfile(config_tmpfile.strpath)

    grader = Grader(
        identity=1,
        config=config,
        applications=[csv_tmpfile.strpath]
    )

    assert len(grader.applications.applicants) == 2


def test_grader_rank(tmpdir, capsys):
    # Basic test, just checking that it down not crash
    config_tmpfile, csv_tmpfile = _tmp_application_files(
        tmpdir, CONF, CSV_APPLICATIONS)
    config = our_configfile(config_tmpfile.strpath)

    grader = Grader(
        identity=1,
        config=config,
        applications=[csv_tmpfile.strpath]
    )

    config['formula']['formula'] = '(nationality!=affiliation)'
    grader.do_rank(args='')

    out, err = capsys.readouterr()
    output_lines = out.replace('-', '').strip().split('\n')[-2:]
    # Mary Jane is first because John's nationality is the same
    # as his affiliation
    assert 'Mary Jane' in output_lines[0]
    assert 'John Doe' in output_lines[1]


def test_grader_rank_labels_filter(tmpdir, capsys):
    # Basic test, just checking that it down not crash
    config_tmpfile, csv_tmpfile = _tmp_application_files(
        tmpdir, CONF, CSV_APPLICATIONS)
    config = our_configfile(config_tmpfile.strpath)

    grader = Grader(
        identity=1,
        config=config,
        applications=[csv_tmpfile.strpath]
    )

    config['formula']['formula'] = '(nationality!=affiliation)'
    grader.do_rank(args='-l RICH')

    out, err = capsys.readouterr()
    output_lines = out.replace('-', '').strip().split('\n')[-1:]
    assert 'John Doe' in output_lines[0]
