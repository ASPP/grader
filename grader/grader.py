import sys
import traceback
import csv
import collections
import textwrap
import pprint
import configfile
import itertools

import cmd_completer
import vector

def printf(fmt, *args, **kwargs):
    print(fmt.format(*args, **kwargs))

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

SCORE_RANGE = (-1, 0, 1)

IDENTITIES = (0, 1)

HOST_COUNTRY = 'Germany'

class Grader(cmd_completer.Cmd_Completer):
    prompt = 'grader> '
    set_completions = cmd_completer.Cmd_Completer.set_completions
    HISTFILE = '~/.grader_history'

    def __init__(self, applications, config, identity):
        super().__init__(histfile=self.HISTFILE)

        self.applications = applications
        self.config = config
        self.identity = identity

    @property
    def formula(self):
        return self.config['formula']['formula']
    @formula.setter
    def formula(self, value):
        # check syntax
        compile(value, '--formula--', 'eval')
        self.config['formula']['formula'] = value

    @property
    def accept_count(self):
        return int(self.config['formula']['accept_count'])
    @accept_count.setter
    def accept_count(self, value):
        self.config['formula']['accept_count'] = value

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
        if self.identity is None:
            raise ValueError('cannot do grading because identity was not set')

        opts = self.grade_options.parse_args(arg.split())

        if opts.what == 'formula':
            if opts.args:
                self.formula = ' '.join(opts.args)
            printf('formula = {}', self.formula)
            return

        for person in self.applications:
            self._grade(person, opts.what)

    rate_options = cmd_completer.ModArgumentParser('rate')\
        .add_argument('what',
                      choices=['programming', 'open_source', 'applied'])\
        .add_argument('args', nargs='*')

    @set_completions('programming', 'open_source', 'applied')
    def do_rate(self, arg):
        "Get rating for activity or set to some value"
        opts = self.rate_options.parse_args(arg.split())
        section = opts.what + '_rating'
        dict = self.config[section]
        if not opts.args:
            pprint.pprint(dict)
        else:
            how = ' '.join(opts.args[:-1])
            value = float(opts.args[-1])
            dict[how] = value

    def _grade(self, person, what):
        assert what in {'motivation', 'cv'}, what
        printf('doing grading for identity {}', self.identity)
        text = getattr(person, what)
        section = self.config[what + '_score']
        scores = section.get(person.fullname, None)
        if scores is None:
            scores = section[person.fullname] = list_of_float()
        old_score = scores[self.identity]
        default = old_score if old_score is not None else ''
        printf('{line}\n{}\n{line}', wrap_paragraphs(text), line='-'*70)
        printf('Old score was {}', old_score)
        while True:
            choice = input('Your choice {} [{}]? '.format(SCORE_RANGE, default))
            if choice == '':
                choice = default
            if choice == '+':
                choice = SCORE_RANGE[-1]
            if choice == '-':
                choice = SCORE_RANGE[0]
            try:
                choice = int(choice)
                if choice not in SCORE_RANGE:
                    raise ValueError('illegal value: {}'.format(choice))
            except ValueError as e:
                print(e)
            else:
                break
        scores[self.identity] = choice
        section[person.fullname] = scores
        printf('{} score set to {}', what, choice)

    def _ranking(self):
        "Order applications by rank"
        if self.formula is None:
            raise ValueError('formula not set yet')

        programming_rating = self.config['programming_rating']
        open_source_rating = self.config['open_source_rating']
        applied_rating = self.config['applied_rating']

        minsc, maxsc = find_min_max(self. formula,
                                    programming_rating,
                                    open_source_rating,
                                    applied_rating)

        for person in self.applications:
            person.score = rank_person(person, self.formula,
                                       programming_rating,
                                       open_source_rating,
                                       applied_rating,
                                       self.config, minsc, maxsc)
        return sorted(self.applications, key=lambda p: p.score, reverse=True)

    def do_rank(self, args):
        if args != '':
            raise ValueError('no args please')

        ranked = self._ranking()
        for rank, person in enumerate(ranked):
            if rank == self.accept_count:
                print('-' * 70)
            printf('{: 2} {p.score:2.1f} {p.name} {p.lastname} <{p.email}>',
                   rank, p=person)

    save_options = cmd_completer.ModArgumentParser('save')\
        .add_argument('filename', nargs='?')

    def do_save(self, args):
        opts = self.save_options.parse_args(args.split())
        self.config.save(opts.filename)

    def do_write(self, args):
        if args != '':
            raise ValueError('no args please')
        ranked = self._ranking()
        print(self.accept_count)
        _write_file('applications_accepted.csv',
                    ranked[:self.accept_count])
        _write_file('applications_rejected.csv',
                    ranked[self.accept_count:])

def _write_file(filename, persons):
    header = '$NAME$;$SURNAME$;$EMAIL$'
    with open(filename, 'w') as f:
        f.write(header + '\n')
        for person in persons:
            row = ';'.join((person.name, person.lastname, person.email))
            f.write(row + '\n')
    printf("'{}' written with header + {} rows", filename, len(persons))

def eval_formula(formula, vars):
    try:
        return eval(formula, vars, {})
    except (NameError, TypeError) as e:
        raise ValueError('formula failed: {}'.format(e))

def rank_person(person, formula,
                programming_rating, open_source_rating, applied_rating,
                config, minsc, maxsc):
    "Apply formula to person and return score"
    vars = {}
    for type in 'programming', 'open_source', 'applied':
        dict = locals().get(type + '_rating')
        key = getattr(person, type)
        key = key.partition('(')[0].partition('/')[0].strip()
                    # remove explanation in () or after /
        try:
            value = dict[key]
        except KeyError:
            raise ValueError('{} not rated for {}'.format(key, type))
                       # from None, when implemented!
        vars[type] = value
    try:
        motivation_score = config['motivation_score'][person.fullname]
        cv_score = config['cv_score'][person.fullname]
    except KeyError as e:
        #raise ValueError('{p.name} {p.lastname}: {e}'.format(p=person, e=e))
        motivation_score = list_of_float()
        cv_score = list_of_float()

    vars.update(born=person.born, # if we decide to implement ageism
                gender=person.gender, # if we decide, ...
                                      # oh we already did
                female=(person.gender == 'Female'),
                nation=person.nation,
                country=person.country,
                motivation=motivation_score.avg(),
                cv=cv_score.avg(),
                email=person.email, # should we discriminate against gmail?
                )
    score = eval_formula(formula, vars)
    assert minsc <= score <= maxsc, (minsc, score, maxsc)
    # scale linearly to SCORE_RANGE/min/max
    range = max(SCORE_RANGE) - min(SCORE_RANGE)
    offset = min(SCORE_RANGE)
    score = (score - minsc) / (maxsc - minsc) * range + offset
    return score

def _yield_values(var, *values):
    for value in values:
        yield var, value

def find_min_max(formula,
                 programming_rating, open_source_rating, applied_rating):
    # coordinate with rank_person!
    options = itertools.product(
        _yield_values('born', 1900, 2012),
        _yield_values('gender', 'M', 'F'),
        _yield_values('female', 0, 1),
        _yield_values('nation', 'Nicaragua', HOST_COUNTRY),
        _yield_values('country', 'Nicaragua', HOST_COUNTRY),
        _yield_values('motivation', *SCORE_RANGE),
        _yield_values('cv', *SCORE_RANGE),
        _yield_values('programming', *programming_rating.values()),
        _yield_values('open_source', *open_source_rating.values()),
        _yield_values('applied', *applied_rating.values()),
        )
    values = [eval_formula(formula, dict(vars)) for vars in options]
    return min(values), max(values)

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
        @property
        def fullname(self):
            return '{p.name} {p.lastname}'.format(p=self)
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


class list_of_float(list):
    def __init__(self, arg=''):
        values = (item.strip() for item in arg.split(','))
        values = [float(value) if value else None for value in values]
        missing = len(IDENTITIES) - len(values)
        if missing < 0:
            raise ValueError('list is too long')
        values += [None] * missing
        super().__init__(values)

    def __str__(self):
        return ', '.join(str(item) if item is not None else '' for item in self)

    def avg(self):
        if True:
            import random
            lst = (item if item is not None else random.choice(SCORE_RANGE)
                   for item in self)
        else:
            lst = self
        return sum(lst) / len(self)


def our_configfile(filename):
    return configfile.ConfigFile(filename,
                                 programming_rating=float,
                                 open_source_rating=float,
                                 applied_rating=float,
                                 formula=str,
                                 motivation_score=list_of_float,
                                 cv_score=list_of_float,
                                 )

grader_options = cmd_completer.ModArgumentParser('grader')\
    .add_argument('applications', type=applications_original,
                  help='CSV file with application data')\
    .add_argument('config', type=our_configfile)\
    .add_argument('-i', '--identity', type=int,
                  choices=IDENTITIES,
                  help='Index of person grading applications')

def main(argv0, *args):
    opts = grader_options.parse_args(args)
    cmd = Grader(opts.applications, opts.config, opts.identity)

    if sys.stdin.isatty():
        while True:
            try:
                cmd.cmdloop()
                break
            except KeyboardInterrupt:
                print()
            except SyntaxError as e:
                print('bad command: %s', e)
            except ValueError as e:
                print('bad value: %s', e)
                traceback.print_exc()
    else:
        input = cmd_completer.InputFile(sys.stdin)
        for line in input:
            cmd.onecmd(line)

if __name__ == '__main__':
    sys.exit(main(*sys.argv))
