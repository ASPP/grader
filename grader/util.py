import numpy as np

from . import cmd_completer
from . import configfile

IDENTITIES = (0, 1, 2, 3)

section_name = '{}_score-{}'.format


class list_of_equivs(list):
    def __init__(self, arg=None):
        equivs = ((item.strip() for item in arg.split('='))
                  if arg is not None else ())
        super().__init__(equivs)

    def __str__(self):
        return ' = '.join(self)


def our_configfile(filename):
    kw = {section_name('motivation', ident):float
          for ident in IDENTITIES}
    with open(filename, 'r') as fileobj:
        config = configfile.ConfigFile(
            fileobj,
            application_lists=str,
            programming_rating=float,
            open_source_rating=float,
            python_rating=float,
            vcs_rating=float,
            underrep_rating=float,
            groups_parameters=int,
            groups_gender_rating=float,
            groups_python_rating=float,
            groups_vcs_rating=float,
            groups_open_source_rating=float,
            groups_programming_rating=float,
            groups_random_seed=str,
            formula=str,
            equivs=list_of_equivs,
            labels=list_of_str,
            fields=list_of_equivs,
            **kw,
        )
    return config


def printf(fmt, *args, **kwargs):
    print(fmt.format(*args, **kwargs))


# like printf above, but this time with explicit flush.
# it should be used everytime you want the strings
# to be print immediately and not only at the end of
# the command
def printff(fmt, *args, **kwargs):
    print(fmt.format(*args, **kwargs))
    cmd_completer.PAGER.flush()


class list_of_float(list):
    def __str__(self):
        return ', '.join(str(item) if item is not None else '-'
                         for item in self)

    def mean(self):
        valid = [arg for arg in self if arg is not None]
        if not valid:
            return float('nan')
        return np.nanmean(valid)


class list_of_str(list):
    def __init__(self, arg=None):
        equivs = ((item.strip() for item in arg.split(','))
                  if arg is not None else ())
        super().__init__(equivs)

    def __str__(self):
        return ', '.join(self)
