from io import StringIO

from .configfile import ConfigFile


CONFIG_STRING_MINIMAL = """
[programming_rating]
competent = 1.0
expert = 0.0
novice = 0.0
"""


def test_configfile_init():
    config_string = StringIO(CONFIG_STRING_MINIMAL)
    config = ConfigFile(
        config_string,
        programming_rating=float,
        python_rating=float,
    )

    # In config
    assert config.cp.has_section('programming_rating')
    assert 'programming_rating' in config.sections
    assert len(list(config.sections['programming_rating'].items())) == 3
    assert config.sections['programming_rating']['competent'] == 1.0

    # Missing from config
    assert config.cp.has_section('python_rating')
    assert 'python_rating' in config.sections
    assert len(list(config.sections['python_rating'].items())) == 0


def test_setting_section_updates_configfile():
    config_string = StringIO(CONFIG_STRING_MINIMAL)
    config = ConfigFile(config_string, programming_rating=float)
    section = config.sections['programming_rating']

    # Update section value
    section['novice'] = -1.0
    assert config.cp.get('programming_rating', 'novice') == '-1.0'

    # Add section value
    section['guru'] = 2.0
    assert config.cp.get('programming_rating', 'guru') == '2.0'


def test_configfile_save(tmpdir):
    config_string = StringIO(CONFIG_STRING_MINIMAL)

    config = ConfigFile(
        config_string,
        programming_rating=float,
        python_rating=float,
    )

    # Make changes
    config.sections['programming_rating']['novice'] = -1.0
    config.sections['python_rating']['competent'] = 100.0

    # Save changes
    config_file = tmpdir.join("temp.conf")
    config.save(config_file.strpath)

    # Reload
    with config_file.open() as f:
        config_reread = ConfigFile(
            f,
            programming_rating=float,
            python_rating=float,
        )

        assert config_reread.sections['programming_rating']['novice'] == -1.0
        assert config_reread.sections['python_rating']['competent'] == 100.0
