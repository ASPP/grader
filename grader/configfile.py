import configparser

class _Section:
    def __init__(self, configparser, section, type):
        self.cp = configparser
        self.section = section
        self.type = type

    def __getitem__(self, item):
        value = self.cp.get(self.section, item)
        if self.type is not None:
            value = self.type(value)
        return value

    def __setitem__(self, item, value):
        self.cp.set(self.section, item, str(value))

class ConfigFile:
    def __init__(self, filename, **sections):
        self.filename = filename
        cp = configparser.ConfigParser(comment_prefixes='#', inline_comment_prefixes='#')
        self.sections = {}
        for section, type in sections.items():
            cp.add_section(section)
            self.sections[section] = _Section(cp, section, type)
        cp.read(filename)
        self.cp = cp

    def __getitem__(self, section):
        return self.sections[section]

    def save(self):
        with open(self.filename, 'w') as f:
            self.cp.write(f)
