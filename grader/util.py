import numpy as np

from . import cmd_completer

class list_of_equivs(list):
    def __init__(self, arg=None):
        equivs = ((item.strip() for item in arg.split('='))
                  if arg is not None else ())
        super().__init__(equivs)

    def __str__(self):
        return ' = '.join(self)


def printf(fmt, *args, **kwargs):
    print(fmt.format(*args, **kwargs))


# like printf above, but this time with explicit flush.
# it should be used everytime you want the strings
# to be print immediately and not only at the end of
# the command
def printff(fmt, *args, **kwargs):
    print(fmt.format(*args, **kwargs))
    cmd_completer.get_pager().flush()


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
        if not isinstance(arg, list):
            arg = ((item.strip() for item in arg.split(','))
                   if arg is not None else ())
        super().__init__(arg)

    def __str__(self):
        return ', '.join(self)


def write_csv_file(filename, fields, rows):
    header = ';'.join(f'${field.upper()}$' for field in fields)
    lines = [header]

    for row in rows:
        assert len(row) == len(fields)
        lines += [';'.join(str(item) for item in row)]

    with open(filename, 'wt') as fl:
        fl.write('\n'.join(lines))
        fl.write('\n')

    printf(f'{filename!r} written with header + {len(rows)} rows')
