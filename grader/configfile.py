import configparser

class _Section:
    def __init__(self, configparser, section, type):
        self.cp = configparser
        self.section = section
        self.type = type

    def __getitem__(self, item):
        try:
            value = self.cp.get(self.section, item)
        except configparser.NoOptionError:
            value = None
        if value is None:
            raise KeyError(item)
        if self.type is not None:
            value = self.type(value)
        return value

    def __setitem__(self, item, value):
        self.cp.set(self.section, item, str(value))

    def get(self, item, fallback):
        try:
            return self.__getitem__(item)
        except KeyError:
            return fallback

    def values(self):
        for name, value in self.cp.items(self.section):
            yield value

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

    def save(self, filename=None):
        filename = filename if filename is not None else self.filename
        with open(filename, 'w') as f:
            self.cp.write(f)
