#!/usr/bin/env python3
import argparse
import collections
import enum
import itertools
import logging
import numbers
import operator
import pathlib
import random
import re
import readline
import sys
import textwrap
import traceback

import numpy as np

try:
    import pandas
except ImportError:
    pandas = None

from . import cmd_completer, vector, applications
from .flags import flags as FLAGS

from .util import (
    list_of_equivs,
    list_of_float,
    printf,
    printff,
    write_csv_file,
)

def ellipsize(s, width):
    return s if len(s) <= width else s[:width-1] + '…'

COLOR = {
    'default': '\x1b[0m',
    'grey'   : '\x1b[1;30m',
    'red'    : '\x1b[1;31m',
    'green'  : '\x1b[1;32m',
    'yellow' : '\x1b[1;33m',
    'blue'   : '\x1b[1;34m',
    'violet' : '\x1b[1;35m',
    'cyan'   : '\x1b[1;36m',
    'bold'   : '\x1b[1m',
    }

def score_color(score):
    color = ('bold' if score is None else
             'violet' if np.isnan(score) else
             'red' if score < 0 else
             'green' if score > 0 else
             'bold')
    return COLOR[color]

def colored_scores(scores):
    return ', '.join('{}{}{}'.format(score_color(score), score, COLOR["default"])
                     for score in scores)

def format_have_applied(person, width=3):
    return '{}{:.{}} {}{}'.format(COLOR['bold'] if person.applied else '',
                                  'ny'[person.applied], width,
                                  person.n_applied,
                                  COLOR['default'] if person.applied else '')

ALMOST_DUMP_FMT = '''\
gender: {p.gender}
institute: {p.institute}
group: {p.group}
affiliation: {p.affiliation}
position: {p.position}{position_other}
appl.prev.: {have_applied}
programming: {p.programming}{programming_description} [{programming}]
python: {p.python} [{python}]
vcs: {p.vcs} [{vcs}]
open source: {p.open_source}{open_source_description} [{open_source}]
'''

DUMP_FMT = '''\
name: %(bold)s{p.name} {p.lastname} {labels}<{p.email}>%(default)s
born: %(bold)s{p.nationality} {p.born}%(default)s
''' % COLOR + ALMOST_DUMP_FMT + '''\
cv: {cv}
motivation: {motivation} [{motivation_scores}]
rank: {{p.rank}} {p.score:6.3f} {{p.highlander}}
travel-grant: {p.travel_grant}
{labels_newline}''' % COLOR

AFFILIATION_FMT = '''\
name: %(yellow)s{p.name} {p.lastname} {labels}<{p.email}>%(default)s
institute: %(bold)s{p.institute}%(default)s
group: %(bold)s{p.group}%(default)s
rank: {{p.rank}} {p.score:6.3f} {p.highlander}
''' % COLOR

MOTIVATION_DUMP_FMT = '''\
appl.prev.: {have_applied}
position: {p.position}{position_other}
programming: {p.programming}{programming_description} [{programming}]
python: {p.python} [{python}]
vcs: {p.vcs} [{vcs}]
open source: {p.open_source}{open_source_description} [{open_source}]
motivation: %(bold)s{motivation}%(default)s\
{labels_newline}''' % COLOR

CV_DUMP_FMT = ALMOST_DUMP_FMT + '''\
motivation: {motivation}
cv: %(bold)s{cv}%(default)s
''' % COLOR

DUMP_FMTS = dict(short=DUMP_FMT,
                 long=DUMP_FMT,
                 group=AFFILIATION_FMT,
                 motivation=MOTIVATION_DUMP_FMT,
                 cv=CV_DUMP_FMT)

_RANK_FMT_LONG = ('{: 4} {p.rank: 4} {labels:{labels_width}} {p.score:6.3f}'
                 ' {p.fullname:{fullname_width}} {email:{email_width}}'
                 ' {institute:{institute_width}} / {group:{group_width}}')
_RANK_FMT_SHORT = ('{: 4} {p.rank: 4} {labels:{labels_width}} {p.score:6.3f}'
                 ' {p.fullname:{fullname_width}} {email:{email_width}}')
_RANK_FMT_DETAILED = ('{: 4} {p.rank: 4} {labels:{labels_width}} {p.score:6.3f}'
                 ' [{motivation_scores}] [appl: {have_applied}]'
                 ' [prog: {programming}] [python: {python}]'
                 ' [{gender:^{gender_width}}] [git: {vcs}]'
                 ' [os: {open_source}]'
                 ' {p.fullname:{fullname_width}} {email:{email_width}}'
                 ' {p.travel_grant}'
                 ' {nationality:{nationality_width}} {affiliation:{affiliation_width}}'
                 ' {institute:{institute_width}} / {group:{group_width}}')
_RANK_FMT_COUNTRY = ('{: 4} {p.rank: 4} {labels:{labels_width}} {p.score:6.3f}'
                 ' {p.fullname:{fullname_width}}'
                 ' {nationality:{nationality_width}} {affiliation:{affiliation_width}}'
                 ' {institute:{institute_width}} / {group:{group_width}}')
RANK_FORMATS = {'short': _RANK_FMT_SHORT,
                'long': _RANK_FMT_LONG,
                'detailed': _RANK_FMT_DETAILED,
                'country': _RANK_FMT_COUNTRY,
                }

DEFAULT_ACCEPT_COUNT = 30

COUNTRY_WIDTH = 10

NOT_AVAILABLE_LABEL = 'NOT AVAILABLE'

LABEL_VALUES = {
    'VIP': 1000,
    'CONFIRMED': 2000,
    'INVITE': 600,
    'INVITESL': 200,
    'SHORTLIST': 100,
    '__nan__': -500, # put people without score near the end of the list, but above those we
                     # explicitly reject
    'DECLINED': -650,
    'NEXT-YEAR': -650,
    'WITHDRAWN': -650,
    'OVERQUALIFIED': -650,
}

class GradingMoves(enum.Enum):
    BACK = enum.auto()
    SKIP = enum.auto()
    NEXT = enum.auto()
    DONE = enum.auto()


class Grader(cmd_completer.Cmd_Completer):
    prompt = COLOR['green']+'grader'+COLOR['yellow']+'>'+COLOR['default']+' '
    set_completions = cmd_completer.Cmd_Completer.set_completions

    def __init__(self, csv_file, identity=None, history_file=None):
        super().__init__(histfile=history_file)

        self.identity = identity
        self.applications = applications.Applications(csv_file=csv_file)
        self.archive = []

        for path in sorted(csv_file.parent.glob('*/applications.csv'),
                              reverse=True):
            # years before 2012 are to be treated less strictly
            relaxed = any(f'{year}-' in str(path) for year in range(2009,2012))
            old = applications.Applications(csv_file=path, relaxed=relaxed)
            self.archive.append(old)

        for person in self.applications:
            person.set_n_applied(self.archive)


    def _set_applied(self, person):
        "Return the number of times a person applied"
        try:
            declared = int(person.applied[0] not in 'nN')
        except AttributeError:
            # this is the first instance of the school and we did not
            # ask about previous participation
            person.applied = 'N'
            person.n_applied = 0
            return
        except IndexError:
            person.n_applied = 0
            return
        found = 0
        for app_old in self.applications_old.values():
            found += (person.fullname in app_old.applicants.fullname or
                      person.email in app_old.applicants.email)
        if found and not declared:
            printf('warning: person found in list says not applied prev.: {} <{}>',
                   person.fullname, person.email)
        if declared and not found:
            printf('warning: person applied prev. not found on lists: {} <{}>',
                   person.fullname, person.email)
        person.n_applied = max(declared, found)

    @property
    def accept_count(self):
        return int(self.applications.ini['formula.accept_count'])

    @accept_count.setter
    def accept_count(self, value):
        self.applications.ini['formula.accept_count'] = value

    def _complete_name(self, prefix):
        """Return a list of dictionaries {name -> [last-name+]}

        Name or last-name must start with prefix.
        """
        completions = collections.defaultdict(set)
        for p in self.applications:
            if p.name.startswith(prefix) or p.lastname.startswith(prefix):
                completions[p.name].add(p.lastname)
        return completions

    identity_options = (
        cmd_completer.PagedArgumentParser('identity')
            .add_argument('identity',
                          nargs='?',
                          help='become this identity')
    )

    def do_identity(self, args):
        "Switch identity"
        opts = self.identity_options.parse_args(args.split())

        if opts.identity:
            known = self.applications.ini.identities()
            if opts.identity not in known:
                raise ValueError(f"Identity {opts.identity} not defined in .ini ({', '.join(known)})")
            self.identity = opts.identity
            print(f'Identity set to {self.identity}')
        else:
            print(f'Running as identity {self.identity}')

    exception_options = (
        cmd_completer.PagedArgumentParser('exception')
            .add_argument('exception',
                          help='the exception type to be raised')
    )

    def do_exception(self, args):
        "Fake command to test exception capturing"
        opts = self.exception_options.parse_args(args.split())
        raise getattr(__builtins__, opts.exception[0])

    autolabel_options = (
        cmd_completer.PagedArgumentParser('autolabel')
            .add_argument('N', type=int, help='length of SHORTLIST')
    )

    def do_autolabel(self, args):
        """Automatically label highlanders as INVITE and the next N as SHORTLIST

        Note: the last ranking is used to sort applications"""
        opts = self.autolabel_options.parse_args(args.split())
        N = opts.N
        try:
            ranked = self.last_ranking
        except AttributeError:
            raise ValueError('You need to rank applications first!')
        counter = 0
        for person in ranked:
            if person.highlander:
                self.applications.add_labels(person.fullname, ['INVITE'])
            else:
                counter += 1
                if counter <= N:
                    self.applications.add_labels(person.fullname, ['SHORTLIST'])
                else:
                    return

    dump_options = (
        cmd_completer.PagedArgumentParser('dump')
            .add_argument('-d', '--detailed', action='store_const',
                          dest='format', const='long', default='short',
                          help='do not truncate free texts')
            .add_argument('-f', '--format',
                          dest='format', choices=DUMP_FMTS.keys(),
                          help='use this format')
            .add_argument('-s', '--sorted', action='store_true',
                          help='print applications sorted by rank')
            .add_argument('-L', '--highlanders', action='store_const',
                          const=True, default=False,
                          help='print applications only for highlanders')
            .add_argument('-l', '--label', type=str, nargs='+', default=(),
                          help='print applications only for people with label')
            .add_argument('-a', '--attribute', nargs='+', metavar='ATTRNAME ATTRVALUE', action='append',
                          help='print applications only for people with matching attributes, '
                          'e.g. -a n_applied 3 -a . Call "-a list" to get a list of attributes.')
            .add_argument('persons', nargs='*',
                          help='name fragments of people to display')
    )

    def do_dump(self, args):
        "Print information about applications"
        opts = self.dump_options.parse_args(args.split())
        persons = tuple(self.applications.filter(label=opts.label))

        if opts.highlanders:
            persons = (p for p in persons if p.highlander)
        if opts.persons:
            persons = (p for p in persons
                       if all(arg in p.fullname for arg in opts.persons))
        if opts.sorted:
            persons = self._ranked(persons)
        if opts.attribute:
            if opts.attribute == [['list']]:
                # generate list of attributes
                attributes = []
                for attr in dir(persons[0]):
                    if attr.startswith('_'):
                        continue
                    attr_value = getattr(persons[0], attr)
                    class_name = type(attr_value).__name__
                    attributes.append((attr, class_name))
                print('List of attributes:', sorted(attributes))
                persons = ()
            else:
                filtered_persons = []
                for p in persons:
                    match = True
                    for attr, value in opts.attribute:
                        if str(getattr(p, attr)) != value:
                            match = False
                            break
                    if match:
                        filtered_persons.append(p)

                persons = filtered_persons

        self._dump(persons, format=opts.format)

    do_dump.completions = _complete_name

    def _dump(self, persons, format='short'):
        for p in persons:
            self._dumpone(p, format=format)

    def _dumpone(self, p, format='short'):
        position_other = \
            (' ({})'.format(p.position_other) if p.position=='Other' else '')
        if format == 'short':
            pd = p.programming_description.replace('\n', ' ')[:72]
            osd = p.open_source_description.replace('\n', ' ')[:72]
            cv = p.cv.replace('\n', ' ')[:72]
            motivation = p.motivation.replace('\n', ' ')[:72]
        else:
            pd = wrap_paragraphs(p.programming_description, 'programming: ') + '\n'
            osd = wrap_paragraphs(p.open_source_description, 'open source: ') + '\n'
            cv = wrap_paragraphs(p.cv, 'cv: ') + '\n'
            motivation = wrap_paragraphs(p.motivation, 'motivation: ') + '\n'
        programming_description = ('\n             {}'.format(pd)
                                   if p.programming_description else '')
        open_source_description = ('\n             {}'.format(osd)
                                   if p.open_source_description else '')
        #labels = p.labels
        if format == 'motivation':
            # hide identifying info from motivation text if in grading mode
            motivation = motivation.replace(p.name, '–')
            motivation = motivation.replace(p.lastname, '–')
        labels = f'[{p.labels}] ' if p.labels else ' '

        # categories = {'programming': self.programming_rating,
        #               'open_source': self.open_source_rating,
        #               'python':      self.python_rating,
        #               'vcs':         self.vcs_rating,
        #               'underrep':    self.underrep_rating}
        # cat_ratings = categorical_ratings(p, categories)
        # cat_ratings = {f'{k}_rating':v for k,v in cat_ratings.items()}

        cat_ratings = {
            'programming': p.get_rating('programming'),
            'open_source': p.get_rating('open_source'),
            'python':      p.get_rating('python'),
            'vcs':         p.get_rating('vcs'),
            'underrep':    p.get_rating('underrep'),
        }

        printf(DUMP_FMTS[format],
               p=p,
               have_applied=format_have_applied(p),
               position_other=position_other,
               programming_description=programming_description,
               open_source_description=open_source_description,
               cv=cv,
               motivation=motivation,
               motivation_scores=colored_scores(p.motivation_scores),
               labels=labels,
               labels_newline=labels + '\n' if labels else '',
               **cat_ratings)

    grep_options = (
        cmd_completer.PagedArgumentParser('grep')
            .add_argument('-n', '--fullname', dest='what', action='store_const',
                          const=operator.attrgetter('fullname'), default=str,
                          help='grep institutes')
            .add_argument('--affiliation', dest='what', action='store_const',
                          const=operator.attrgetter('affiliation'), default=str,
                          help='grep affiliation')
            .add_argument('--nationality', dest='what', action='store_const',
                          const=operator.attrgetter('nationality'), default=str,
                          help='grep nationality')
            .add_argument('--institute', dest='what', action='store_const',
                          const=operator.attrgetter('institute'),
                          help='grep institutes')
            .add_argument('-g', '--group', dest='what', action='store_const',
                          const=operator.attrgetter('group'),
                          help='grep groups')
            .add_argument('-l', '--long', dest='format',
                          action='store_const', const='long', default='short',
                          help='provide full listing')
            .add_argument('pattern',
                          help='pattern to look for')
    )

    def do_grep(self, args):
        "Look for string in applications"
        opts = self.grep_options.parse_args(args.split())
        which = (p for p in self.applications
                 if re.search(opts.pattern, opts.what(p)))
        self._dump(which, format=opts.format)


    def print_grading_stats(self, applications):
        if pandas is None:
            print('need pandas to show stats!')
            return
        grades = pandas.DataFrame(list(self._get_gradings(p)) for p in applications)
        stats = grades.apply(pandas.value_counts, dropna=False).fillna(0)
        stats.rename(index={'nan':'todo', 'NaN':'todo'}, inplace=True)
        print(stats)


    formula_options = (
        cmd_completer.PagedArgumentParser('formula')
            .add_argument('expression', nargs='*')
    )

    def do_formula(self, arg):
        """Display or set the formula

        Formula is set with:
          grade formula ...
        where ... is a python expression using the following variables:
          born: int,
          gender: 'M' or 'F' or 'O',
          nonmale: 0 or 1,
          nationality: str,
          affiliation: str,
          motivation: float,
          programming: float,
          open_source: float,
          applied: 0 or 1 or 2 or ...,
          python: float,
          labels: list of str.
        """

        opts = self.formula_options.parse_args(arg.split())

        # First check if the formula seems valid
        if opts.expression:
            formula = ' '.join(opts.expression)
            self.applications.check_formula(formula)
            self.applications.ini.formula = formula

        minsc, maxsc, contr = self.applications.find_min_max()

        printf('formula = {}', self.applications.ini.formula)
        printf('score ∈ [{:6.3f},{:6.3f}]', minsc, maxsc)
        printf('applied ∈ {}', self.applications.all_applied())
        print('contributions:')
        # print single contributions
        field_width = max(len(item[0].strip()) for item in contr.items())
        items = sorted(contr.items(), key=operator.itemgetter(1), reverse=True)
        for item in items:
            printf('{:{w}} : {:4.1f}%', item[0].strip(), item[1], w=field_width)



    grade_options = (
        cmd_completer.PagedArgumentParser('grade')
            .add_argument('-s', '--stat', action='store_true',
                          help='display statics about the grading process itself')
            .add_argument('-g', '--graded', type=int,
                          nargs='?', const=all, metavar='SCORE',
                          help='grade already graded too, optionally with specified score')
            .add_argument('-l', '--label', nargs='+', default=(),
                          help='show only people with all of those labels')
            .add_argument('-d', '--disagreement', type=int,
                          nargs='?', const=all, metavar='WHO',
                          help='grade people who have a >1 pt difference')
            .add_argument('person', nargs='*')
    )

    def do_grade(self, arg):
        """Assign points to motivation statements
        """

        opts = self.grade_options.parse_args(arg.split())
        if opts.graded is not None and opts.person:
            raise ValueError('cannot use --graded option with explicit name')

        if opts.label:
            applications = self.applications.filter(label=opts.label)
        else:
            applications = list(self.applications)

        fullname = ' '.join(opts.person)

        if self.identity is None:
            raise ValueError('cannot do grading because identity was not set (use -i param or identity verb)')

        if opts.graded is not None or opts.disagreement is not None:
            grade = opts.graded if opts.graded is not None else all
            todo = [p for p in applications
                    if grade is all or self._get_grading(p) == grade]
            total = len(todo)
        elif fullname:
            todo = [p for p in applications if p.fullname == fullname]
            total = len(todo)
        else:
            todo = [p for p in applications
                    if self._get_grading(p) is None]
            total = len(self.applications)

        if opts.disagreement is not None:
            if opts.disagreement is all:
                dis_todo = []
                for p in todo:
                    gradings = [g if g is not None else 0 for g in self._get_gradings(p)]
                    if (max(gradings) - min(gradings)) > 1:
                        dis_todo.append(p)
                todo = dis_todo
            else:
                todo = [p for p in todo
                        if (self._get_grading(p) is not None and
                            self._get_grading(p, identity=opts.disagreement) is not None and
                            abs(self._get_grading(p) -
                                self._get_grading(p, identity=opts.disagreement)) > 1)]
            total = len(todo)

        done_already = total - len(todo)

        if opts.stat:
            self.print_grading_stats(applications)
            return

        printff('Doing grading for identity {}', self.identity)
        printff('Press ^C or ^D to stop')

        random.shuffle(todo)

        pos = 0

        while True:
            if pos >= len(todo):
                break

            progress = '┃ {:.1%} done, {} left to go ┃'.format((pos + done_already) / total,
                                                               len(todo) - pos)
            sep_up = '\n┏'+(len(progress)-2)*'━'+'┓\n'
            sep_down = '\n┗'+(len(progress)-2)*'━'+'┛\n'
            print(sep_up+progress+sep_down)
            print()

            match self.grade_one_motivation(todo[pos], opts.disagreement is not None):
                case GradingMoves.NEXT | GradingMoves.SKIP:
                    pos += 1
                case GradingMoves.BACK:
                    pos = max(0, pos - 1)
                case GradingMoves.DONE:
                    break

    do_grade.completions = _complete_name

    RATING_CATEGORIES = ['programming', 'open_source', 'python', 'vcs', 'underrep']

    rate_options = (
        cmd_completer.PagedArgumentParser('rate')
            .add_argument('-m', '--missing', action='store_true',
                          help='rate all missing fields')
            .add_argument('what', nargs='?',
                          choices=RATING_CATEGORIES)
            .add_argument('args', nargs='*')
    )

    @set_completions(*RATING_CATEGORIES)
    def do_rate(self, arg):
        "Get rating for activity or set to some value"
        opts = self.rate_options.parse_args(arg.split())
        if opts.missing and opts.args:
            raise SyntaxError('cannot use -m with arguments')

        if opts.what is None:
            whats = self.RATING_CATEGORIES
        else:
            whats = [opts.what]

        for what in whats:
            if opts.what is None:
                printf('== {} ==', what)
            section = what + '_rating'
            current = self.config[section]
            if opts.args:
                how = ' '.join(opts.args[:-1])
                value = float(opts.args[-1])
                current[how] = value
            else:
                current.print_sorted()
                if opts.missing:
                    used = set(getattr(p, what).lower()
                               for p in self.applications)
                    for descr in used:
                        try:
                            get_rating(what, current, descr)
                        except MissingRating as e:
                            raw = input('{} = '.format(descr))
                            value = float(raw)
                            current[e.key] = value

    def _get_grading(self, person, identity=None):
        if identity is None:
            identity = self.identity
        return person.get_motivation_score(identity)

    def _get_gradings(self, person):
        gen = (self._get_grading(person, identity) for identity in self.applications.ini.identities())
        return list_of_float(gen)

    def _set_grading(self, person, score):
        assert isinstance(score, numbers.Number), score
        person.set_motivation_score(score, identity=self.identity)
        printff('Motivation score set to {}', score)

    def grade_one_motivation(self, person, disagreement):
        "This is the function that does the loop asking question +1/0/-1/…"
        if disagreement:
            scores = self._get_gradings(person)
        else:
            scores = [self._get_grading(person)]
        old_score = self._get_grading(person)
        default = old_score if old_score is not None else ''
        self._dumpone(person, format='motivation')

        printff(f'Old score was {colored_scores(scores)}')

        def is_valid_score(choice):
            try:
                choice = int(choice)
                return choice in applications.SCORE_RANGE
            except:
                return False

        valid_choice = None
        while valid_choice not in applications.SCORE_RANGE:
            prompt = 'Your choice {}/b/s/d/l LABEL [{}]? '.format(applications.SCORE_RANGE, default)
            try:
                choice = input(prompt)
            except EOFError:
                print()
                return GradingMoves.DONE

            if len(choice) <= 2:
                clen = readline.get_current_history_length()
                if readline.get_history_item(clen) == choice: # 1-based numbering
                    readline.remove_history_item(clen - 1)    # 0-based numbering

            match choice.split():
                case [choice] if is_valid_score(choice):
                    valid_choice = int(choice)
                case ['+']:
                    valid_choice = 1
                case ['=']:
                    valid_choice = 0
                case ['-']:
                    valid_choice = -1
                case ['b']:
                    printff('going back one')
                    return GradingMoves.BACK
                case ['s'] | []:
                    printff('person skipped')
                    return GradingMoves.SKIP
                case ['d']:
                    printff('showing person on request')
                    self._dumpone(person, format='long')
                case ['l']:
                    printff('{}', ', '.join(person.labels) or '(no labels)')
                case ['l', *labels]:
                    for label in labels:
                        remove = label.startswith('-')
                        lname = label[1:] if remove else label

                        if remove:
                            mod = person.remove_label(lname)
                            if mod:
                                printff('Removed label {} = {}', person.fullname, lname)
                            else:
                                printff('(label not found)')
                        else:
                            mod = person.add_label(lname)
                            if mod:
                                printff('Added label {} = {}', person.fullname, lname)
                            else:
                                printff('(label already set)')
                case _:
                    print('illegal value: {}'.format(choice))

        if valid_choice != default:
            self._set_grading(person, valid_choice)
        return GradingMoves.NEXT

    def _score_with_labels(self, p, use_labels=False):
        add_score = 0

        if use_labels:
            for label, value in LABEL_VALUES.items():
                if label in p.labels:
                    add_score += value
                elif label=='INVITESL' and any('INVITESL' in l for l in p.labels):
                    add_score += value

        return p.calculate_score() + add_score

    def _group_institute(self, person):
        group = self._equiv_master(person.group)
        institute = self._equiv_master(person.institute)
        return institute + ' | ' + group

    def _assign_rankings(self, use_labels=False):
        "Order applications by rank"
        ini = self.applications.ini
        if ini.formula is None:
            raise ValueError('formula not set yet')

        nan_to_value = lambda n: LABEL_VALUES['__nan__'] if np.isnan(n) else n

        ordered = sorted(self.applications.people,
                         key=lambda p: nan_to_value(self._score_with_labels(p, use_labels=use_labels)),
                         reverse=True)

        rank, prevscore = 0, 10000
        highlander = True
        labs = {}
        count = 0
        # rank fairly now
        for person in ordered:
            lab = self._group_institute(person)
            person.samelab = highlander and lab in labs

            #if 'VIP' in self._labels(person.fullname):
            #    assert rank == 0, (rank, count, person.fullname, person.score)
            #    person.rank = 0
            #    person.highlander = True
            #    count += 1
            #    continue

            if person.samelab:
                finalrank = labs[lab]
            else:
                if person.score != prevscore:
                    rank += 1
                finalrank = labs[lab] = rank

            count += 1
            if highlander and person.score != prevscore and count > self.accept_count:
                highlander = False

            person.rank = finalrank
            person.highlander = highlander
            prevscore = person.score
        return ordered

    def _ranked(self, applicants=None, use_labels=False):
        ranked = self._assign_rankings(use_labels=use_labels)

        if applicants is not None:
            applicants_names = [p.fullname for p in applicants]
            ranked_applications = [p for p in ranked if p.fullname in applicants_names]
        else:
            ranked_applications = ranked

        return vector.vector(ranked_applications)

    def _equiv_master(self, variant):
        """ Return the key for equiv canonicalization. """
        for key, values in self.applications.ini['equivs'].items():
            if (variant.lower() == key.lower() or
                variant.lower() in (spelling.lower() for spelling in values)):
                return key
        return variant.strip()

    rank_options = (
        cmd_completer.PagedArgumentParser('rank')
            .add_argument('-s', '--short', action='store_const',
                          dest='format', const='short', default='long',
                          help='show only names and emails')
            .add_argument('--use-labels', action='store_true', default=True,
                          help=argparse.SUPPRESS)
            .add_argument('-n', '--no-labels', action='store_false', dest='use_labels',
                          help="don't use labels in ranking")
            .add_argument('-l', '--label', nargs='+', default=(),
                          help='show only people with all of those labels')
            .add_argument('-f', '--format', choices=RANK_FORMATS.keys(),
                          help='use format')
            .add_argument('-c', '--column-width',
                          dest='width', type=int, default=20,
                          help='specify width of institute and group columns')
    )

    def do_rank(self, args):
        "Print list of people sorted by ranking"
        opts = self.rank_options.parse_args(args.split())
        people = self.applications.filter(label=opts.label)
        ranked = self._ranked(people, use_labels=opts.use_labels)
        self.last_ranking = ranked
        fullname_width = min(max(len(field) for field in ranked.fullname), opts.width)
        email_width = max(len(field) for field in ranked.email) + 2
        institute_width = min(max(len(self._equiv_master(field)) for field in ranked.institute), opts.width)
        group_width = min(max(len(self._equiv_master(field)) for field in ranked.group), opts.width)
        affiliation_width = min(max(len(field) for field in ranked.affiliation), COUNTRY_WIDTH)
        nationality_width = min(max(len(field) for field in ranked.nationality), COUNTRY_WIDTH)
        labels_width = max(len(str(self.applications.ini.get_labels(field)))
                           for field in ranked.fullname) or 1

        fmt = RANK_FORMATS[opts.format]
        prev_highlander = True
        print(COLOR['grey']+'-' * 70+COLOR['default'])
        for pos, person in enumerate(ranked):
            if prev_highlander and not person.highlander:
                print(COLOR['grey']+'-' * 70+COLOR['default'])
            prev_highlander = person.highlander
            labels = person.labels
            if 'CONFIRMED' in labels:
                line_color = COLOR['bold']
            elif 'NEXT-YEAR' in labels:
                line_color = COLOR['red']
            elif 'DECLINED' in labels:
                line_color = COLOR['red']
            elif 'INVITE' in labels and 'CONFIRMED' not in labels:
                line_color = COLOR['yellow']
            elif any('INVITESL' in label for label in labels) and not 'INVITE' in labels:
                line_color = COLOR['green']
            elif 'SHORTLIST' in labels and 'INVITE' not in labels:
                line_color = COLOR['cyan']
            else:
                line_color = COLOR['grey']

            group = self._equiv_master(person.group)
            institute = self._equiv_master(person.institute)

            categories = {
                'programming': self.applications.ini.get_ratings("programming"),
                'open_source': self.applications.ini.get_ratings("open_source"),
                'python':      self.applications.ini.get_ratings("python"),
                'vcs':         self.applications.ini.get_ratings("vcs"),
                'underrep':    self.applications.ini.get_ratings("underrep"),
            }
            cat_scores = categorical_scores(person, categories)
            cat_scores = {f'{k}_score':v for k,v in cat_scores.items()}

            # share the space for name and email to avoid overflows
            name_width_adj = min(len(person.fullname) - fullname_width, email_width - len(person.email) - 2)
            name_width_adj = max(name_width_adj, 0)

            printf(line_color + fmt + COLOR['default'], pos + 1, p=person,
                   email='<{}>'.format(person.email),
                   have_applied=format_have_applied(person, 1),
                   gender=person.gender,
                   gender_width=len('female'),
                   fullname_width=fullname_width + name_width_adj,
                   email_width=email_width - name_width_adj,
                   institute='—' if person.samelab else
                             ellipsize(institute, opts.width),
                   institute_width=institute_width,
                   group=ellipsize(group, opts.width),
                   group_width=group_width,
                   nationality=ellipsize(person.nationality, nationality_width),
                   nationality_width=nationality_width,
                   affiliation=ellipsize(person.affiliation, affiliation_width),
                   affiliation_width=affiliation_width,
                   labels=', '.join(labels),
                   labels_width=labels_width,
                   motivation_scores=colored_scores(self._get_gradings(person)),
                   **cat_scores)

    stat_options = (
        cmd_completer.PagedArgumentParser('stat')
            .add_argument('-d', '--detailed', action='store_true', default=False,
                          help='display detailed statistics')
            .add_argument('--use-labels', action='store_true', default=True,
                          help=argparse.SUPPRESS)
            .add_argument('-n', '--no-labels', action='store_false', dest='use_labels',
                          help="don't use labels in ranking")
            .add_argument('-L', '--highlanders', action='store_true',
                          help='display statistics only for highlanders')
            .add_argument('-l', '--labels',
                          help='display statistics only for people with LABELS. '
                               'Multiple labels: INVITE,CONFIRMED or INVITE,-,DECLINED')
            .add_argument('--edition', default='current',
                          help="edition for which we want the stats, e.g. '2010-trento'. "
                               "'all' means all editions. 'current' (default) means the "
                               "latest one")
    )

    def do_stat(self, args):
        "Display statistics"
        opts = self.stat_options.parse_args(args.split())
        edition = opts.edition

        if edition == 'current':
            applicants = list(self.applications)
        elif edition == 'all':
            applicants = list(self.applications)
            for school, app_old in self.applications_old.items():
                applicants = applicants + vector.vector(list(app_old))
        else:
            applicants = list(self.applications_old[edition])

        if opts.highlanders:
            ranked = self._ranked(applicants, use_labels=opts.use_labels)
            pool = [person for person in ranked if person.highlander]
        else:
            pool = applicants

        if opts.labels:
            # create label filter tuple
            labels = opts.labels.split(',')
            pool = self.applications.filter(label=labels)

        self._compute_and_print_stats(pool, opts.detailed)

    def _compute_and_print_stats(self, pool, detailed):
        """ Given a pool of applicants, compute and display some statistics.
        """
        observables = ['born', 'gender', 'nationality', 'affiliation',
                       'position', 'applied', 'n_applied', 'open_source',
                       'programming', 'python', 'vcs', 'underrep']
        counters = {var: collections.Counter(getattr(p, var, NOT_AVAILABLE_LABEL)
                                             for p in pool)
                    for var in observables}

        length = {var: len(counters[var]) for var in observables}
        applicants = len(pool)
        FMT_STAT = '{:<26.26} = {:>5d}'
        FMT_STAP = FMT_STAT + ' ({:4.1f}%)'
        printf(FMT_STAT, 'Pool', applicants)
        printf(FMT_STAT, 'Nationalities', length['nationality'])
        printf(FMT_STAT, 'Countries of affiliation', length['affiliation'])
        g = counters['gender']
        # normalise gender counters (old editions used capitalized gender names)
        g['female'] = g['female'] + g['Female']
        g['male'] = g['male'] + g['Male']
        printf(FMT_STAP, 'Gender: other',  g['other'],  g['other'] / applicants * 100)
        printf(FMT_STAP, 'Gender: female', g['female'], g['female'] / applicants * 100)
        printf(FMT_STAP, 'Gender: male', g['male'],   g['male'] / applicants * 100)
        for pos in counters['position'].most_common():
            printf(FMT_STAP, 'Position: '+pos[0], pos[1], pos[1] / applicants * 100)
        if detailed:
            for var in observables:
                print('--\n'+var.upper())
                if var in ('born', 'n_applied'):
                    # years should be sorted numerically and not by popularity
                    for n in sorted(counters[var].items(),
                            key=operator.itemgetter(0)):
                        printf(FMT_STAP, str(n[0]), n[1], n[1] / applicants * 100)
                else:
                    for n in sorted(counters[var].items(),
                                    key=operator.itemgetter(1), reverse=True):
                        printf(FMT_STAP, str(n[0]), n[1], n[1] / applicants * 100)

    def _wiki_tb_head(self, items):
        strs = (str(x) for x in items)
        print('^ '+' ^ '.join(strs)+' ^')

    def _wiki_tb_row(self, items):
        strs = (str(x) for x in items)
        print('| '+' | '.join(strs)+' |')

    def _wiki_pc(self, num, tot):
        pc = ' (%.1f%%)'
        return str(num)+pc%(num/tot*100)

    def do_wiki(self, args):
        "Dump statistics of CONFIRMED people for the Wiki."
        confirmed = tuple(self.applications.filter(label=('CONFIRMED')))
        applicants = list(self.applications)
        print('==== Students ====')
        # we want first a list of confirmed with names/nationality/affiliations
        self._wiki_tb_head(('Firstname', 'Lastname', 'Nationality', 'Affiliation'))
        for person in sorted(confirmed, key=operator.attrgetter('name')):
            natflag = '{{:flags:%s'%FLAGS[person.nationality].lower()+'.png}}'
            affflag = '{{:flags:%s'%FLAGS[person.affiliation].lower()+'.png}}'
            self._wiki_tb_row((person.name, person.lastname,
                               natflag+' '+person.nationality,
                               affflag+' '+person.affiliation))

        print('\n\n=== Statistics ===')
        self._wiki_tb_head(('','Applicants', 'Participants'))

        # first collect statistics like we do in the do_stat method (DRY ;))))
        observables = ['born', 'gender', 'nationality', 'affiliation',
                       'position', 'applied', 'n_applied', 'open_source',
                       'programming', 'python', 'vcs', 'underrep']
        c_confirmed = {var: collections.Counter(getattr(p, var, NOT_AVAILABLE_LABEL)
                                                for p in confirmed)
                       for var in observables}
        c_applicants = {var: collections.Counter(getattr(p, var, NOT_AVAILABLE_LABEL)
                                                 for p in applicants)
                       for var in observables}

        Na = len(applicants)
        Nc = len(confirmed)


        self._wiki_tb_row(('Pool', Na, Nc))
        self._wiki_tb_row(('Nationalities',
                           len(c_applicants['nationality']),
                           len(c_confirmed['nationality'])))
        self._wiki_tb_row(('Countries of affiliation',
                           len(c_applicants['affiliation']),
                           len(c_confirmed['affiliation'])))
        for gender in ('other', 'female', 'male'):
            self._wiki_tb_row(('Gender: %s'%gender,
                               self._wiki_pc(c_applicants['gender'][gender], Na),
                               self._wiki_pc(c_confirmed['gender'][gender], Nc)))

        for pos, count in c_applicants['position'].most_common():
            self._wiki_tb_row(('Position: %s'%pos,
                               self._wiki_pc(count, Na),
                               self._wiki_pc(c_confirmed['position'].get(pos, 0), Nc)))

        print('\n\n== Details for Participants ==')
        for var in observables:
            self._wiki_tb_head((var.upper(), 'Count'))
            if var in ('born', 'n_applied'):
                for n in sorted(c_confirmed[var].items(),
                                key=operator.itemgetter(0)):
                    self._wiki_tb_row((n[0],
                                       self._wiki_pc(n[1], Nc)))
            else:
                for n in sorted(c_confirmed[var].items(),
                                key=operator.itemgetter(1), reverse=True):
                    self._wiki_tb_row((n[0],
                                       self._wiki_pc(n[1], Nc)))
            print()

    def do_equiv(self, args):
        "Specify institutions'/labs' names as equivalent"
        if args == '':
            for key, value in self.config['equivs'].items():
                printf('{} = {}', key, value)
            return

        variant, *equivs = [item.strip() for item in args.split('=')]
        saved = self.config['equivs'].get(variant, list_of_equivs())
        saved.extend(equivs)
        self.config['equivs'][variant] = saved
        self.ranking_done = False



    label_options = (
        cmd_completer.PagedArgumentParser('label')
            .add_argument('arg',
                          nargs='+',
                          help="Full name or index of the person to add a label to")
    )

    def do_label(self, args):
        """Mark persons with string labels

        label First Last = LABEL   # add label
        label First Last =         # delete labels
        label First Last           # display labels
        label                      # display all labels
        label LABEL                # display people thus labelled
        """

        opts = self.label_options.parse_args(args.split())

        applications = self.applications
        if not opts.arg:
            for applicant in applications:
                if applicant.labels:
                    print('{} = {}'.format(applicant.fullname.lower(),
                                           applicant.labels))
            return

        if '=' in opts.arg:
            idx = opts.arg.index('=')
            fullname = " ".join(opts.arg[:idx])
            labels = opts.arg[idx+1:]

            if labels:
                for label in labels:
                    applications.ini.add_label(fullname, label)
            else:
                applications.ini.set_labels(fullname, [])
        else:
            fullname = " ".join(opts.arg)
            display_by_label = any(label in opts.arg
                                   for label in applications.all_labels())
            if display_by_label:
                for label in opts.arg:
                    count = 0
                    printf('== {} ==', label)
                    for applicant in applications:
                        if label in applicant.labels:
                            printf('{}. {}', count, applicant.fullname.lower())
                            count += 1
                    printf('== {} labelled ==', count)
            else:
                applicant = applications[fullname]
                labels = applicant.labels
                if labels:
                    printf('{} = {}', fullname, labels)
                else:
                    printf('{} has no labels', fullname)

    do_label.completions = _complete_name

    save_options = (
        cmd_completer.PagedArgumentParser('save')
            .add_argument('filename', nargs='?')
    )

    def do_save(self, args):
        "Save the fruits of thy labour"
        opts = self.save_options.parse_args(args.split())
        self.applications.ini.save(opts.filename)

    dumpcsv_options = (
            cmd_completer.PagedArgumentParser('dumpcsv')
                .add_argument('-l', '--labels',
                              help='only dump people with LABELS. '
                                   'Multiple labels: INVITE,CONFIRMED or INVITE,-,DECLINED')
                .add_argument('-a', '--attributes',
                              required=True,
                              help='comma-separated list of attributes to dump')
    )


    def do_dumpcsv(self, args):
        opts = self.dumpcsv_options.parse_args(args.split())

        labels = opts.labels.split(',') if opts.labels else []
        attributes = opts.attributes.split(',')

        # TODO: make the output name configurable?
        self.applications.write_to_file('/tmp/grader.csv', labels, attributes)


    def do_write(self, args):
        """Write lists of mailing recipients

        Labels have the following precedence:
        - DECLINE - person cancelled, let's forget about them
        - CONFIRMED - person is coming, let's forget about them for now
        - INVITE - person to invite
        - SHORTLIST - person to potentially invite
        - OVERQUALIFIED - persons that are too good to be here
        - CUSTOM-ANSWER - person is rejected but needs a custom answer
        - REJECTED - the rest
        """
        if args != '':
            raise ValueError('no args please')

        self.applications.write_filtered_csv('list_confirmed.csv',
                                             ('CONFIRMED', '-', 'DECLINED', 'NEXT-YEAR'))

        self.applications.write_filtered_csv('list_invite.csv',
                                             ('INVITE', '-', 'DECLINED', 'CONFIRMED', 'NEXT-YEAR'))

        self.applications.write_filtered_csv('list_invite_reminder.csv',
                                             ('INVITE', '-', 'DECLINED', 'CONFIRMED', 'NEXT-YEAR'))

        self.applications.write_filtered_csv('list_overqualified.csv',
                                             ('OVERQUALIFIED', '-', 'CUSTOM-ANSWER'))

        self.applications.write_filtered_csv('list_custom_answer.csv',
                                             ('CUSTOM-ANSWER',))

        # get all INVITESL? labels
        invitesl = [label for label in self.applications.all_labels()
                    if label.startswith('INVITESL')]

        self.applications.write_filtered_csv('list_shortlist.csv',
                                             ('SHORTLIST', '-', 'DECLINED', 'NEXT-YEAR', 'CONFIRMED', 'INVITE', *invitesl))

        for i, sl_label in enumerate(invitesl, start=1):
            persons = applications.filter(labels=(sl_label, '-', 'CONFIRMED', 'DECLINED', 'NEXT-YEAR'))

            fields = [*itertools.chain.from_iterable(('{d}name', '{d}lastname') for d in range(1, len(persons) + 1)),
                      'email']

            row = [*itertools.chain.from_iterable((p.name, p.lastname) for p in persons),
                   ','.join(p.email for p in persons)]

            write_csv_file('list_same_lab{i}.csv', fields, [row])

        self.applications.write_filtered_csv('list_invite_nextyear.csv',
                                             ('NEXT-YEAR',))

        self.applications.write_filtered_csv('list_rejected.csv',
                                             ('-', 'DECLINED', 'NEXT-YEAR', 'CONFIRMED', 'INVITE', 'SHORTLIST',
                                              'OVERQUALIFIED', 'CUSTOM-ANSWER', *invitesl))

        self.applications.write_filtered_csv('list_declined.csv',
                                             ('DECLINED', '-', 'NEXT-YEAR'))


class MissingRating(KeyError):
    def __str__(self, *args):
        return '{} not rated for "{}"'.format(*self.args)
    @property
    def key(self):
        return self.args[1]

def get_rating(name, dict, key, fallback=None):
    """Retrieve rating.

    Explanation in () or after / is ignored in the key.

    Throws MissingRating if rating is not present.
    """
    if key == '':
        key = '(none)'
    else:
        key = key.partition('(')[0].partition('/')[0].strip().partition(',')[0].strip()
    try:
        return dict[key]
    except KeyError:
        if fallback is not None:
            return fallback
    raise MissingRating(name, key)

def categorical_scores(person, categories):
    return {c: person.get_rating(c) for c in categories}

    # vars = {}
    # for attr, dict in categories.items():
    #     # Some attributes might not be defined by Person. Let's not define the
    #     # variable in that case. This will cause the formula evaluation to fail
    #     # if it refers to one of the undefined attributes.
    #     try:
    #         key = getattr(person, attr)
    #     except AttributeError:
    #         pass
    #     else:
    #         value = get_rating(attr, dict, key)
    #         vars[attr] = value
    # return vars

def wrap_paragraphs(text, prefix=''):
    prefix = '\n' + ' ' * len(prefix)
    paras = text.strip().split('\n\n')
    wrapped = (prefix.join(prefix.join(textwrap.wrap(line.strip()))
                           for line in para.split('\n'))
               for para in paras)
    return ('\n'+prefix).join(wrapped)


grader_options = (
    cmd_completer.ModArgumentParser('grader')
        .add_argument('-i', '--identity',
                      help='Index of person grading applications')
        .add_argument('--history-file',
                      type=pathlib.Path,
                      default=pathlib.Path('~/.grader_history').expanduser(),
                      help='File to record typed in commands')
        .add_argument('applications',
                      nargs='?',
                      type=pathlib.Path,
                      default=pathlib.Path('applications.csv'),
                      help='CSV file with application data')
)

def main():
    logging.basicConfig(level=logging.INFO)

    opts = grader_options.parse_args()

    cmd = Grader(
        csv_file=opts.applications,
        history_file=opts.history_file,
    )

    # Set identity in a way that checks that the identity is known
    if opts.identity:
        cmd.do_identity(opts.identity)

    if sys.stdin.isatty():
        while True:
            try:
                cmd.cmdloop()
                break
            except KeyboardInterrupt:
                print()
            except SyntaxError as e:
                printff('bad command: {}', e)
            except ValueError as e:
                printff('bad value: {}', e)
                traceback.print_exc()
            except Exception as e:
                printff('programming error: {}', e)
                traceback.print_exc()
    else:
        input = cmd_completer.InputFile(sys.stdin)
        for line in input:
            cmd.onecmd(line)

    if cmd.applications.ini.has_modifications():
        cmd.applications.ini.save()


if __name__ == '__main__':
    sys.exit(main())
