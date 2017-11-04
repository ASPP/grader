from io import StringIO

from configfile import ConfigFile


def test_configfile_init():
    config_string = StringIO("""
    [programming_rating]
    competent = 1.0
    expert = 0.0
    novice = 0.0
    """)

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
