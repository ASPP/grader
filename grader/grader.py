import sys
import traceback
import csv
import collections

import cmd_completer
import vector

def printf(fmt, *args, **kwargs):
    return print(fmt.format(*args, **kwargs))

dump_fmt = '''\
name: {p.name} {p.lastname} <{p.email}>
born: {p.nation} {p.born}
gender: {p.gender}
institute: {p.institute}
group: {p.group}
country: {p.country}
position: {p.position}{position_other}
appl.prev.: {p.applied}
programming: {p.programming}{programming_description}
python: {p.python}
open source: {p.open_source}{open_source_description}
'''

class Grader(cmd_completer.Cmd_Completer):
    prompt = 'grader> '
    HISTFILE = '~/.grader_history'

    def __init__(self, applications):
        super().__init__(histfile=self.HISTFILE)

        self.applications = applications

    def do_dump(self, arg):
        for p in self.applications:
            position_other = \
                (' ({})'.format(p.position_other)
                 if p.position=='Other' else '')
            programming_description = \
                ('\nprogramming: {.programming_description:.72}'.format(p)
                 if p.programming_description else '')
            open_source_description = \
                ('\nopen source: {.open_source_description:.72}'.format(p)
                 if p.open_source_description else '')
            printf(dump_fmt,
                   p=p,
                   position_other=position_other,
                   programming_description=programming_description,
                   open_source_description=open_source_description)


@vector.vectorize
def csv_file(filename, names):
    reader = csv.reader(open(filename, newline=''))
    header = next(reader)
    assert len(header) == 21
    class Person(collections.namedtuple('Person', names)):
        pass
    while True:
        yield Person(*next(reader))

def applications_original(filename):
    names = """completed
               nation born gender
               institute group country
               position position_other
               applied
               programming python programming_description
               open_source open_source_description
               motivation cv
               name lastname email
               token"""
    return csv_file(filename, names)

grader_options = cmd_completer.ModArgumentParser('grader')\
    .add_argument('applications', type=applications_original,
                  help='CSV file with application data')

def main(argv0, *args):
    opts = grader_options.parse_args(args)
    cmd = Grader(opts.applications)

    if sys.stdin.isatty():
        while True:
            try:
                cmd.cmdloop()
                break
            except KeyboardInterrupt:
                print
            except SyntaxError as e:
                log.exception('bad command: %s', e)
            except ValueError as e:
                log.exception('bad value: %s', e)
                traceback.print_exc()
    else:
        input = cmd_completer.InputFile(sys.stdin)
        for line in input:
            cmd.onecmd(line)

if __name__ == '__main__':
    sys.exit(main(*sys.argv))
