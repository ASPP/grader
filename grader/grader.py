import sys
import traceback
import csv
import collections
import textwrap

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

score_range = (-1, 0, 1)

class Grader(cmd_completer.Cmd_Completer):
    prompt = 'grader> '
    set_completions = cmd_completer.Cmd_Completer.set_completions
    HISTFILE = '~/.grader_history'

    def __init__(self, applications):
        super().__init__(histfile=self.HISTFILE)

        self.applications = applications
        self.formula = None

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

    grade_options = cmd_completer.ModArgumentParser('grade')\
        .add_argument('what', choices=['motivation', 'cv', 'formula'],
                      help='what to grade | set formula')\
        .add_argument('args', nargs='*')

    @set_completions('motivation', 'cv', 'formula')
    def do_grade(self, arg):
        "Assign points to motivation or CV statements"
        opts = self.grade_options.parse_args(arg.split())

        if opts.what == 'formula':
            if opts.args:
                self.formula = ' '.join(opts.args)
            printf('formula is {}', self.formula)
            return

        for person in self.applications:
            self._grade(person, opts.what)


    def _grade(self, person, what):
        assert what in {'motivation', 'cv'}, what
        text = getattr(person, what)
        old_score = getattr(person, what + '_score', None)
        default = old_score if old_score is not None else ''
        printf('{line}\n{}\n{line}', wrap_paragraphs(text), line='-'*70)
        printf('Old score was {}', old_score)
        while True:
            choice = input('Your choice {} [{}]? '.format(score_range, default))
            if choice == '':
                choice = default
            if choice == '+':
                choice = score_range[-1]
            if choice == '-':
                choice = score_range[0]
            try:
                choice = int(choice)
                if choice not in score_range:
                    raise ValueError('illegal value: {}'.format(choice))
            except ValueError as e:
                print(e)
            else:
                break
        setattr(person, what + '_score', choice)
        printf('{} score set to {}', what, choice)

def wrap_paragraphs(text):
    paras = text.strip().split('\n\n')
    wrapped = ('\n'.join(textwrap.wrap(para)) for para in paras)
    return '\n\n'.join(wrapped)

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
