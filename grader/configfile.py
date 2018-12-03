import configparser
import operator
import collections

class _Section:
    def __init__(self, configparser, section, type=str):
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
        value = self.type(value)
        return value

    def __setitem__(self, item, value):
        self.cp.set(self.section, item, str(value))

    def get(self, item, fallback):
        try:
            return self.__getitem__(item)
        except KeyError:
            return fallback

    def create(self, item, fallback=None):
        if fallback is None:
            fallback = self.type
        try:
            return self.__getitem__(item)
        except KeyError:
            value = fallback()
            self.__setitem__(item, value)
            return value

    def clear(self, *keys):
        for key in keys or self.keys():
            self.cp.remove_option(self.section, key)

    def keys(self):
        for name, value in self.cp.items(self.section):
            yield name

    def values(self):
        for name, value in self.cp.items(self.section):
            yield self.type(value)

    def items(self):
        for name, value in self.cp.items(self.section):
            yield name, self.type(value)

    def print_sorted(self):
        for key, val in sorted(self.items(), key=operator.itemgetter(1)):
            print(key, '=', val)

class ConfigFile:
    def __init__(self, config_files, **sections):
        config_parser = configparser.ConfigParser(
            comment_prefixes='#',
            inline_comment_prefixes='#',
        )
        config_parser.read(config_files)

        self.sections = collections.OrderedDict()
        for section, type in sections.items():
            if not config_parser.has_section(section):
                config_parser.add_section(section)
            self.sections[section] = _Section(
                config_parser, section, type)

        self.cp = config_parser
        self.filename = config_files[-1]

    def __getitem__(self, section):
        return self.sections[section]

    def save(self, filename=None):
        filename = filename if filename is not None else self.filename
        with open(filename, 'w') as f:
            self.cp.write(f)
