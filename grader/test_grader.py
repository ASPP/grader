from textwrap import dedent

from grader import Applications


def _tmp_application_files(tmpdir, config_string, csv_string):
    config_tmpfile = tmpdir.join('test_grader.conf')
    config_tmpfile.write(config_string)
    csv_tmpfile = tmpdir.join('test_applications.csv')
    csv_tmpfile.write(csv_string)
    return config_tmpfile, csv_tmpfile


def test_applications_from_paths(tmpdir):
    config_string = dedent("""
        [labels]
        john doe = VEGAN
        """)
    csv_string = dedent("""
        "First name","Last name","Email address"
        "John","Doe","john.dow@nowhere.com"
        "Mary Jane","Smith","mary82@something.org"
        """).strip()
    config_tmpfile, csv_tmpfile = _tmp_application_files(
        tmpdir, config_string, csv_string)

    fields_to_col_names_section = {
        'name': ['First name'],
        'lastname': ['Last name'],
        'email': ['email'],
    }

    applications = Applications.from_paths(
        config_tmpfile.strpath,
        csv_tmpfile.strpath,
        fields_to_col_names_section
    )

    assert len(applications.applicants) == 2
    assert applications.applicants[0].name == 'John'
    assert applications.applicants[1].lastname == 'Smith'
    assert applications.applicants[0].labels == ['VEGAN']
