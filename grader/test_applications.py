from io import StringIO
from textwrap import dedent

from pytest import raises

from configfile import ConfigFile
from applications import Applications, build_person_factory
from util import list_of_str


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


def test_applications_init():
    config_string = dedent("""
    [labels]
    john doe = VEGAN, VIP
    """)
    config = ConfigFile(StringIO(config_string), labels=list_of_str)

    person_factory = build_person_factory(['name', 'lastname'])
    applicants = [person_factory('John', 'Doe')]

    applications = Applications(applicants, config)

    assert len(applications.applicants) == 1
    assert applications.applicants[0].labels == ['VEGAN', 'VIP']


def test_applications_find_applicant_by_fullname():
    config_string = dedent("""
    [labels]
    john doe = VEGAN
    """)
    config = ConfigFile(StringIO(config_string), labels=list_of_str)

    person_factory = build_person_factory(['name', 'lastname'])
    applicants = [person_factory('John', 'Doe')]

    applications = Applications(applicants, config)
    john_doe = applications.find_applicant_by_fullname('john doe')
    assert applications.applicants[0] is john_doe

    with raises(ValueError):
        applications.find_applicant_by_fullname('johnny mnemonic')


def test_applications_add_labels():
    config_string = dedent("""
    [labels]
    john doe = VEGAN
    """)
    config = ConfigFile(StringIO(config_string), labels=list_of_str)

    person_factory = build_person_factory(['name', 'lastname'])
    john_doe = person_factory('John', 'Doe')
    ben_johnson = person_factory('Ben', 'Johnson')
    applicants = [john_doe, ben_johnson]

    applications = Applications(applicants, config)
    applications.add_labels('john doe', ['VIP', 'VIRULENT'])
    applications.add_labels('ben johnson', ['VIPER'])

    assert john_doe.labels == ['VEGAN', 'VIP', 'VIRULENT']
    assert config.sections['labels']['john doe'] \
           == ['VEGAN', 'VIP', 'VIRULENT']

    assert ben_johnson.labels == ['VIPER']
    assert config.sections['labels']['ben johnson'] == ['VIPER']


def test_applications_clear_labels():
    config_string = dedent("""
    [labels]
    john doe = VEGAN, VIP
    """)
    config = ConfigFile(StringIO(config_string), labels=list_of_str)

    person_factory = build_person_factory(['name', 'lastname'])
    john_doe = person_factory('John', 'Doe')
    applicants = [john_doe]

    applications = Applications(applicants, config)

    assert john_doe.labels == ['VEGAN', 'VIP']
    assert 'john doe' in config.sections['labels'].keys()
    applications.clear_labels('john doe')
    assert john_doe.labels == []
    assert 'john doe' not in config.sections['labels'].keys()


def test_applications_get_labels():
    config_string = dedent("""
    [labels]
    john doe = VEGAN, VIP
    """)
    config = ConfigFile(StringIO(config_string), labels=list_of_str)

    person_factory = build_person_factory(['name', 'lastname'])
    john_doe = person_factory('John', 'Doe')
    ben_johnson = person_factory('Ben', 'Johnson')
    applicants = [john_doe, ben_johnson]

    applications = Applications(applicants, config)
    assert applications.get_labels('john doe') == ['VEGAN', 'VIP']
    assert applications.get_labels('ben johnson') == []


def test_applications_get_all_labels():
    config_string = dedent("""
    [labels]
    john doe = VEGAN, VIP
    ben johnson = VIPER
    """)
    config = ConfigFile(StringIO(config_string), labels=list_of_str)

    person_factory = build_person_factory(['name', 'lastname'])
    john_doe = person_factory('John', 'Doe')
    ben_johnson = person_factory('Ben', 'Johnson')
    applicants = [john_doe, ben_johnson]

    applications = Applications(applicants, config)
    assert applications.get_all_labels() == {'VEGAN', 'VIP', 'VIPER'}

def test_applications_filter_attributes():
    config_string = dedent("""
    [labels]
    """)
    config = ConfigFile(StringIO(config_string), labels=list_of_str)

    person_factory = build_person_factory(['name', 'lastname', 'nationality', 'gender'])
    mario_rossi = person_factory('Mario', 'Rossi', 'Italy', 'Male')
    lucia_bianchi = person_factory('Lucia', 'Bianchi', 'Italy', 'Female')
    fritz_lang = person_factory('Fritz', 'Lang', 'Germany', 'Male')
    applicants = [mario_rossi, fritz_lang, lucia_bianchi]

    applications = Applications(applicants, config)
    assert applications.filter(nationality='Italy') == [mario_rossi, lucia_bianchi]
    assert applications.filter(nationality='Italy', female=True) == [lucia_bianchi]
    assert applications.filter(nationality='Germany') == [fritz_lang]
    assert applications.filter(nationality='NoCountryForOldMen') == []
    with raises(AttributeError):
        applications.filter(dummy='Error')

def test_applications_filter_labels():
    config_string = dedent("""
    [labels]
    mario rossi = ALFA, DELTA, MIKE
    fritz lang = ZULU, DELTA, MIKE, ECHO
    """)
    config = ConfigFile(StringIO(config_string), labels=list_of_str)

    person_factory = build_person_factory(['name', 'lastname'])
    mario_rossi = person_factory('Mario', 'Rossi')
    fritz_lang = person_factory('Fritz', 'Lang')
    applicants = [mario_rossi, fritz_lang]

    applications = Applications(applicants, config)
    assert applications.filter(label='ALFA') == [mario_rossi]
    assert applications.filter(label='ZULU') == [fritz_lang]
    assert applications.filter(label=('ALFA', 'MIKE')) == [mario_rossi]
    assert applications.filter(label=('DELTA','MIKE')) == [mario_rossi, fritz_lang]
    assert applications.filter(label=('DELTA', 'MIKE', '-', 'ECHO')) == [mario_rossi]
    assert applications.filter(label=('DELTA', 'MIKE', '-', 'ECHO', 'ALFA')) == []
    assert applications.filter(label='NOLABEL') == []

def test_applications_iteration():
    config_string = ""
    config = ConfigFile(StringIO(config_string), labels=list_of_str)

    person_factory = build_person_factory(['name', 'lastname'])
    mario_rossi = person_factory('Mario', 'Rossi')
    fritz_lang = person_factory('Fritz', 'Lang')
    applicants = [mario_rossi, fritz_lang]

    applications = Applications(applicants, config)
    result = []
    for app in applications:
        result.append(app)
    assert result == applications.applicants
    # test that we can call len
    assert len(applications) == len(applications.applicants)

