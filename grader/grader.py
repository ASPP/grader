#!/usr/bin/env python3
import argparse
import collections
import contextlib
import io
import itertools
import keyword
import logging
import math
import numbers
import numpy as np
import operator
import os
import pprint
import random
import re
import sys
import tempfile
import textwrap
import token
import tokenize
import traceback
try:
    import pandas
except ImportError:
    pandas = None

from . import cmd_completer
from .flags import flags as FLAGS
from . import vector

from .applications import (
    parse_applications_csv_file,
    Applications,
)
from .util import (
    list_of_equivs,
    list_of_float,
    our_configfile,
    printf,
    printff,
    section_name,
    IDENTITIES,
)


@contextlib.contextmanager
def Umask(umask):
    old = os.umask(umask)
    try:
        yield
    finally:
        os.umask(old)

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

ALMOST_DUMP_FMT = '''\
gender: {p.gender}
institute: {p.institute}
group: {p.group}
affiliation: {p.affiliation}
position: {p.position}{position_other}
appl.prev.: {p.applied} {p.napplied}
programming: {p.programming}{programming_description} [{programming_score}]
python: {p.python} [{python_score}]
vcs: {p.vcs} [{vcs_score}]
open source: {p.open_source}{open_source_description} [{open_source_score}]
vcs: {p.vcs}
'''

DUMP_FMT = '''\
name: %(bold)s{p.name} {p.lastname} {labels}<{p.email}>%(default)s
born: %(bold)s{p.nationality} {p.born}%(default)s
''' % COLOR + ALMOST_DUMP_FMT + '''\
cv: {cv}
motivation: {motivation} [{motivation_scores}]
rank: {p.rank} {p.score} {p.highlander}
travel-grant: {p.travel_grant}
{labels_newline}''' % COLOR

AFFILIATION_FMT = '''\
name: %(yellow)s{p.name} {p.lastname} {labels}<{p.email}>%(default)s
institute: %(bold)s{p.institute}%(default)s
group: %(bold)s{p.group}%(default)s
rank: {p.rank} {p.score} {p.highlander}
''' % COLOR

MOTIVATION_DUMP_FMT = '''\
appl.prev.: {p.applied} {p.napplied}
position: {p.position}{position_other}
programming: {p.programming}{programming_description} [{programming_score}]
python: {p.python} [{python_score}]
vcs: {p.vcs} [{vcs_score}]
open source: {p.open_source}{open_source_description} [{open_source_score}]
vcs: {p.vcs}
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
                 ' [{motivation_scores}] [appl: {p.applied} {p.napplied}]'
                 ' [prog: {programming_score}] [python: {python_score}]'
                 ' [prog: {vcs_score}] [vcs: {vcs_score}]'
                 ' [os: {open_source_score}]'
                 ' {p.fullname:{fullname_width}} {email:{email_width}}'
                 ' {p.travel_grant}')
_RANK_FMT_COUNTRY = ('{: 4} {p.rank: 4} {labels:{labels_width}} {p.score:6.3f}'
                 ' {p.fullname:{fullname_width}}'
                 ' {nationality:{nationality_width}} {affiliation:{affiliation_width}}'
                 ' {institute:{institute_width}} / {group:{group_width}}')
RANK_FORMATS = {'short': _RANK_FMT_SHORT,
                'long': _RANK_FMT_LONG,
                'detailed': _RANK_FMT_DETAILED,
                'country': _RANK_FMT_COUNTRY,
                }

SCORE_RANGE = (-1, 0, 1)

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
    'WITHDRAWN': -650,
    'OVERQUALIFIED': -650,
}

def equal(a, b):
    # Fuck people who designed this nan != nan crap.
    # Fuck people who implemented it in Python like blind sheep.
    if isinstance(a, float) and isinstance(b, float):
        if np.isnan(a) == np.isnan(b):
            return True
        if np.isnan(a) != np.isnan(b):
            return False
        # use normal comparison otherwise
    return a == b

class Grader(cmd_completer.Cmd_Completer):
    prompt = COLOR['green']+'grader'+COLOR['yellow']+'>'+COLOR['default']+' '
    set_completions = cmd_completer.Cmd_Completer.set_completions
    HISTFILE = '~/.grader_history'

    def __init__(self, identity, config, applications):
        super().__init__(histfile=self.HISTFILE)

        self.identity = identity
        self.config = config
        self._init_applications(applications)
        self.modified = False
        self.ranking_done = False

    def _init_applications(self, application_filenames):
        section = self.config['application_lists']
        if application_filenames:
            section.clear()
            for i, filename in zip('abcdefghijkl', application_filenames):
                section[i] = filename
        else:
            application_filenames = list(section.values())

        fields_to_col_names_section = self.config['fields']
        if len(list(fields_to_col_names_section.keys())) == 0:
            raise ValueError('[fields] section is mandatory')

        # Load applications for current edition.
        with open(application_filenames[0], newline='', encoding='utf-8-sig') as f:
            applicants = parse_applications_csv_file(
                f, fields_to_col_names_section)
        self.applications = Applications(applicants, self.config)

        # Load applications for previous editions.
        self.applications_old = {}
        for filename in application_filenames:
            if filename == 'applications.csv':
                continue

            path = filename.split('/')[0]
            config_path = os.path.join(path, 'grader.conf')
            app = Applications.from_paths(
                config_path=config_path,
                csv_path=filename,
                fields_to_col_names_section=fields_to_col_names_section,
            )
            self.applications_old[path] = app

        for applicant in self.applications:
            self._set_applied(applicant)

    def _set_applied(self, person):
        "Return the number of times a person applied"
        try:
            declared = int(person.applied[0] not in 'nN')
        except AttributeError:
            # this is the first instance of the school and we did not
            # ask about previous participation
            person.applied = 'N'
            person.napplied = 0
            return
        except IndexError:
            person.napplied = 0
            return
        found = 0
        for app_old in self.applications_old.values():
            found += (person.fullname in app_old.applicants.fullname or
                      person.email in app_old.applicants.email)
        if found and not declared:
            printf('warning: person found in list says not applied prev.: {}',
                   person.fullname)
        if declared and not found:
            printf('warning: person applied prev. not found on lists: {}',
                   person.fullname)
        person.napplied = max(declared, found)

    def _applied_range(self):
        s = set(p.napplied for p in self.applications)
        return sorted(s)

    @property
    def formula(self):
        try:
            return self.config['formula']['formula']
        except KeyError:
            return None
    @formula.setter
    def formula(self, value):
        # check syntax
        compile(value, '--formula--', 'eval')
        self.config['formula']['formula'] = value
        # invalidate rankings
        self.ranking_done = False

    @property
    def location(self):
        try:
            return self.config['formula']['location']
        except KeyError:
            return None
    @location.setter
    def location(self, value):
        self.config['formula']['location'] = value
        # invalidate rankings
        self.ranking_done = False

    @property
    def accept_count(self):
        return int(self.config['formula'].create('accept_count',
                                                 lambda:DEFAULT_ACCEPT_COUNT))
    @accept_count.setter
    def accept_count(self, value):
        self.config['formula']['accept_count'] = value

    @property
    def programming_rating(self):
        return self.config['programming_rating']
    @property
    def open_source_rating(self):
        return self.config['open_source_rating']
    @property
    def python_rating(self):
        return self.config['python_rating']
    @property
    def vcs_rating(self):
        return self.config['vcs_rating']
    @property
    def underrep_rating(self):
        return self.config['underrep_rating']

    def _complete_name(self, prefix):
        """Return a list of dictionaries {name -> [last-name+]}

        Name or last-name must start with prefix.
        """
        completions = collections.defaultdict(set)
        for p in self.applications:
            if p.name.startswith(prefix) or p.lastname.startswith(prefix):
                completions[p.name].add(p.lastname)
        return completions

    identity_options = cmd_completer.PagedArgumentParser('identity')\
        .add_argument('identity', type=int, choices=IDENTITIES,
                      help='become this identity')

    def do_identity(self, args):
        "Switch identity"
        opts = self.identity_options.parse_args(args.split())
        self.identity = opts.identity

    exception_options = cmd_completer.PagedArgumentParser('exception')\
        .add_argument('exception',
                      help='the exception type to be raised')

    def do_exception(self, args):
        "Fake command to test exception capturing"
        opts = self.exception_options.parse_args(args.split())
        raise getattr(__builtins__, opts.exception[0])

    dump_options = cmd_completer.PagedArgumentParser('dump')\
        .add_argument('-d', '--detailed', action='store_const',
                      dest='format', const='long', default='short',
                      help='do not truncate free texts')\
        .add_argument('-f', '--format',
                      dest='format', choices=DUMP_FMTS.keys(),
                      help='use this format')\
        .add_argument('-s', '--sorted', action='store_true',
                      help='print applications sorted by rank')\
        .add_argument('-L', '--highlanders', action='store_const',
                      const=True, default=False,
                      help='print applications only for highlanders')\
        .add_argument('-l', '--label', type=str, nargs='+', default=(),
                      help='print applications only for people with label')\
        .add_argument('-a', '--attribute', type=str, nargs=2, metavar=('ATTRNAME', 'ATTRVALUE'),
                      help='print applications only for people with matching attributes'
                      ', e.g. -a napplied 3. Call "-a list list" to get a list of attributes.')\
        .add_argument('persons', nargs='*',
                      help='name fragments of people to display')

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
            attributes = persons[0]._fields
            if opts.attribute == ['list', 'list']:
                print('List of attributes:', attributes)
                persons = ()
            # we need to consume all persons to see the final list of all attributes,
            # because persons[0] may not have all of them. e.g. napplied...
            # maybe not worth just to display an error message...
            #elif opts.attribute[0] not in attributes:
            #    print('Attribute', opts.attribute[0], 'not known!')
            #    persons = ()
            else:
                persons = (p for p in persons if str(getattr(p, opts.attribute[0])) == opts.attribute[1])

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
        labels = self.applications.get_labels(p.fullname)
        if format == 'motivation':
            # hide identifying info from motivation text if in grading mode
            motivation = motivation.replace(p.name, '–')
            motivation = motivation.replace(p.lastname, '–')
        if labels:
            labels = '[{}] '.format(labels)

        categories = {'programming': self.programming_rating,
                      'open_source': self.open_source_rating,
                      'python':      self.python_rating,
                      'vcs':         self.vcs_rating,
                      'underrep':    self.underrep_rating}
        cat_scores = categorical_scores(p, categories)
        cat_scores = {f'{k}_score':v for k,v in cat_scores.items()}

        printf(DUMP_FMTS[format],
               p=p,
               position_other=position_other,
               programming_description=programming_description,
               open_source_description=open_source_description,
               cv=cv,
               motivation=motivation,
               motivation_scores=self._gradings(p, 'motivation'),
               labels=labels,
               labels_newline=labels + '\n' if labels else '',
               **cat_scores)

    grep_options = cmd_completer.PagedArgumentParser('grep')\
        .add_argument('-n', '--fullname', dest='what', action='store_const',
                      const=operator.attrgetter('fullname'), default=str,
                      help='grep institutes')\
        .add_argument('--affiliation', dest='what', action='store_const',
                      const=operator.attrgetter('affiliation'), default=str,
                      help='grep affiliation')\
        .add_argument('--nationality', dest='what', action='store_const',
                      const=operator.attrgetter('nationality'), default=str,
                      help='grep nationality')\
        .add_argument('--institute', dest='what', action='store_const',
                      const=operator.attrgetter('institute'),
                      help='grep institutes')\
        .add_argument('-g', '--group', dest='what', action='store_const',
                      const=operator.attrgetter('group'),
                      help='grep groups')\
        .add_argument('-l', '--long', dest='format',
                      action='store_const', const='long', default='short',
                      help='provide full listing')\
        .add_argument('pattern',
                      help='pattern to look for')

    def do_grep(self, args):
        "Look for string in applications"
        opts = self.grep_options.parse_args(args.split())
        which = (p for p in self.applications
                 if re.search(opts.pattern, opts.what(p)))
        self._dump(which, format=opts.format)


    def print_grading_stats(self, what, applications):
        if pandas is None:
            print('need pandas to show stats!')
            return
        grades = pandas.DataFrame(list(self._gradings(p, what)) for p in applications)
        stats = grades.apply(pandas.value_counts, dropna=False).fillna(0)
        stats.rename(index={'nan':'todo', 'NaN':'todo'}, inplace=True)
        print(stats)

    grade_options = cmd_completer.PagedArgumentParser('grade')\
        .add_argument('what', choices=['motivation', 'cv', 'formula', 'location'],
                      help='what to grade | set formula | set location')\
        .add_argument('-s', '--stat', action='store_true',
                      help='display statics about the grading process itself')\
        .add_argument('-g', '--graded', type=int,
                      nargs='?', const=all, metavar='SCORE',
                      help='grade already graded too, optionally with specified score')\
        .add_argument('-l', '--label', nargs='+', default=(),
                      help='show only people with all of those labels')\
        .add_argument('-d', '--disagreement', type=int,
                      nargs='?', const=all, metavar='WHO',
                      help='grade people who have a >1 pt difference')\
        .add_argument('person', nargs='*')

    @set_completions('formula',
                     motivation=_complete_name)
    def do_grade(self, arg):
        """Assign points to motivation statements or set formula/location

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

        Location is set with:
           set location
        """

        opts = self.grade_options.parse_args(arg.split())
        if opts.graded is not None and opts.person:
            raise ValueError('cannot use --graded option with explicit name')

        if opts.what == 'formula':
            if opts.person:
                self.formula = ' '.join(opts.person)
                self.modified = True
            minsc, maxsc, contr = find_min_max(self.formula, self.location,
                                               self.programming_rating,
                                               self.open_source_rating,
                                               self.python_rating,
                                               self.vcs_rating,
                                               self.underrep_rating,
                                               self._applied_range())

            printf('formula = {}', self.formula)
            printf('score ∈ [{:6.3f},{:6.3f}]', minsc, maxsc)
            printf('applied ∈ {}', self._applied_range())
            print('contributions:')
            # print single contributions
            field_width = max(len(item[0].strip()) for item in contr.items())
            items = sorted(contr.items(), key=operator.itemgetter(1), reverse=True)
            for item in items:
                printf('{:{w}} : {:4.1f}%', item[0].strip(), item[1], w=field_width)
            return
        elif opts.what == 'location':
            if opts.person:
                self.location = ' '.join(opts.person)
                self.modified = True
            printf('location = {}', self.location)
            return

        if opts.label:
            applications = self.applications.filter(label=opts.label)
        else:
            applications = list(self.applications)

        fullname = ' '.join(opts.person)

        if self.identity is None:
            raise ValueError('cannot do grading because identity was not set (use -i param or identity verb)')

        if opts.graded is not None or opts.disagreement:
            grade = opts.graded if opts.graded is not None else all
            todo = [p for p in applications
                    if grade is all or self._get_grading(p, opts.what) == grade]
            total = len(todo)
        elif fullname:
            todo = [p for p in applications if p.fullname == fullname]
            total = len(todo)
        else:
            todo = [p for p in applications
                    if self._get_grading(p, opts.what) is None]
            total = len(self.applications)

        if opts.disagreement is not None:
            if opts.disagreement is all:
                todo = [p for p in todo
                        if (max(self._gradings(p, opts.what), default=0) -
                            min(self._gradings(p, opts.what), default=0) > 1)]
            else:
                todo = [p for p in todo
                        if (self._get_grading(p, opts.what) is not None and
                            self._get_grading(p, opts.what, opts.disagreement) is not None and
                            abs(self._get_grading(p, opts.what) -
                                self._get_grading(p, opts.what, opts.disagreement)) > 1)]
            total = len(todo)

        done_already = total - len(todo)

        if opts.stat:
            self.print_grading_stats(opts.what, applications)
            return

        printff('Doing grading for identity {}', self.identity)
        printff('Press ^C or ^D to stop')

        random.shuffle(todo)
        for num, person in enumerate(todo):
            progress = '┃ {:.1%} done, {} left to go ┃'.format((num + done_already) / total,
                                                             len(todo) - num)
            sep_up = '\n┏'+(len(progress)-2)*'━'+'┓\n'
            sep_down = '\n┗'+(len(progress)-2)*'━'+'┛\n'
            print(sep_up+progress+sep_down)
            print()
            if not self._grade(person, opts.disagreement is not None):
                break

    RATING_CATEGORIES = ['programming', 'open_source', 'python', 'vcs', 'underrep']

    rate_options = cmd_completer.PagedArgumentParser('rate')\
        .add_argument('-m', '--missing', action='store_true',
                      help='rate all missing fields')\
        .add_argument('what', nargs='?',
                      choices=RATING_CATEGORIES)\
        .add_argument('args', nargs='*')

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
                self.modified = True
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
                            self.modified = True

    def _get_grading(self, person, what, identity=None):
        if identity is None:
            identity = self.identity
        section = self.config[section_name(what, identity)]
        return section.get(person.fullname, None)

    def _gradings(self, person, what):
        gen = (
            self.config[section_name(what, identity)].get(person.fullname, None)
            for identity in IDENTITIES)
        return list_of_float(gen)

    def _set_grading(self, person, what, score):
        assert isinstance(score, numbers.Number), score
        section = self.config[section_name(what, self.identity)]
        section[person.fullname] = score
        printff('{} score set to {}', what, score)
        self.modified = True

    def _grade(self, person, disagreement):
        if disagreement:
            scores = self._gradings(person, 'motivation')
        else:
            scores = [self._get_grading(person, 'motivation')]
        old_score = self._get_grading(person, 'motivation')
        default = old_score if old_score is not None else ''
        self._dumpone(person, format='motivation')
        scores = ['%({})s{}%(default)s'.format('bold' if score is None else
                                               'violet' if np.isnan(score) else
                                               'red' if score < 0 else
                                               'green' if score > 0 else
                                               'bold', score) % COLOR
                  for score in scores]
        printff('Old score was {}', ', '.join(scores))
        while True:
            prompt = 'Your choice {}/s/d/l LABEL [{}]? '.format(SCORE_RANGE, default)
            try:
                choice = input(prompt)
            except EOFError:
                print()
                return False

            if choice == 's' or choice == '' and default == '':
                printff('person skipped')
                return True
            elif choice == 'd':
                printff('showing person on request')
                self._dumpone(person, format='long')
                continue
            elif choice.startswith('l '):
                labels = choice.split()[1:]
                printff('labelling {} as {}',
                        person.fullname, ', '.join(labels))
                self.applications.add_labels(person.fullname, labels)
                continue
            elif choice == '':
                choice = default
            elif choice == '+':
                choice = SCORE_RANGE[-1]
            elif choice == '-':
                choice = SCORE_RANGE[0]
            elif 'abstain'.startswith(choice) and len(choice) >= 3: # abs…
                choice = np.nan

            if isinstance(choice, float) and np.isnan(choice):
                break

            try:
                choice = int(choice)
                if choice not in SCORE_RANGE:
                    raise ValueError('illegal value: {}'.format(choice))
                break
            except ValueError as e:
                printff(str(e))

        if not equal(choice, default):
            self._set_grading(person, 'motivation', choice)
        return True

    def _score_with_labels(self, p, use_labels=False):
        if not use_labels:
            return p.score

        add_score = 0
        for label, value in LABEL_VALUES.items():
            if label in p.labels:
                add_score += value
            elif label=='INVITESL' and any('INVITESL' in l for l in p.labels):
                add_score += value
        return p.score + add_score

    def _group_institute(self, person):
        group = self._equiv_master(person.group)
        institute = self._equiv_master(person.institute)
        return institute + ' | ' + group

    def _assign_rankings(self, use_labels=False):
        "Order applications by rank"
        if self.formula is None:
            raise ValueError('formula not set yet')

        #if self.ranking_done:
        #    return
        #else:
        #    self.ranking_done = True
        minsc, maxsc, contr = find_min_max(self.formula, self.location,
                                           self.programming_rating,
                                           self.open_source_rating,
                                           self.python_rating,
                                           self.vcs_rating,
                                           self.underrep_rating,
                                           self._applied_range())

        categories = {'programming': self.programming_rating,
                      'open_source': self.open_source_rating,
                      'python':      self.python_rating,
                      'vcs':         self.vcs_rating,
                      'underrep':    self.underrep_rating}

        for person in self.applications:
            labels = self.applications.get_labels(person.fullname)
            person.score = rank_person(person,
                                       self.formula, self.location,
                                       categories,
                                       self._gradings(person, 'motivation'),
                                       minsc, maxsc,
                                       labels,
                                       person.napplied)

        nan_to_value = lambda n: LABEL_VALUES['__nan__'] if np.isnan(n) else n

        ordered = sorted(self.applications,
                         key=lambda x: nan_to_value(self._score_with_labels(x, use_labels=use_labels)),
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

    def _ranked(self, applicants=None, use_labels=False):
        self._assign_rankings(use_labels=use_labels)

        if applicants is None:
            applicants = list(self.applications)

        ranked = sorted(applicants, key=lambda p: (p.rank, self._group_institute(p)))
        return vector.vector(ranked)

    def _equiv_master(self, variant):
        "Return the key for equiv canocalization"
        for key, values in self.config['equivs'].items():
            if (variant.lower() == key.lower() or
                variant.lower() in (spelling.lower() for spelling in values)):
                return key
        return variant.strip()

    rank_options = cmd_completer.PagedArgumentParser('rank')\
        .add_argument('-s', '--short', action='store_const',
                      dest='format', const='short', default='long',
                      help='show only names and emails')\
        .add_argument('--use-labels', action='store_true', default=True,
                      help=argparse.SUPPRESS)\
        .add_argument('-n', '--no-labels', action='store_false', dest='use_labels',
                      help="don't use labels in ranking")\
        .add_argument('-l', '--label', nargs='+', default=(),
                      help='show only people with all of those labels')\
        .add_argument('-f', '--format', choices=RANK_FORMATS.keys(),
                      help='use format')\
        .add_argument('-c', '--column-width',
                      dest='width', type=int, default=20,
                      help='specify width of institute and group columns')

    def do_rank(self, args):
        "Print list of people sorted by ranking"
        opts = self.rank_options.parse_args(args.split())
        people = self.applications.filter(label=opts.label)
        ranked = self._ranked(people, use_labels=opts.use_labels)
        fullname_width = min(max(len(field) for field in ranked.fullname), opts.width)
        email_width = max(len(field) for field in ranked.email) + 2
        institute_width = min(max(len(self._equiv_master(field)) for field in ranked.institute), opts.width)
        group_width = min(max(len(self._equiv_master(field)) for field in ranked.group), opts.width)
        affiliation_width = min(max(len(field) for field in ranked.affiliation), COUNTRY_WIDTH)
        nationality_width = min(max(len(field) for field in ranked.nationality), COUNTRY_WIDTH)
        labels_width = max(len(str(self.applications.get_labels(field)))
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

            categories = {'programming': self.programming_rating,
                          'open_source': self.open_source_rating,
                          'python':      self.python_rating,
                          'vcs':         self.vcs_rating,
                          'underrep':    self.underrep_rating}
            cat_scores = categorical_scores(person, categories)

            # share the space for name and email to avoid overflows
            name_width_adj = min(len(person.fullname) - fullname_width, email_width - len(person.email) - 2)
            name_width_adj = max(name_width_adj, 0)

            printf(line_color + fmt + COLOR['default'], pos + 1, p=person,
                   email='<{}>'.format(person.email),
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
                   motivation_scores=self._gradings(person, 'motivation'),
                   **cat_scores)

    stat_options = (
        cmd_completer.PagedArgumentParser('stat')
            .add_argument('-d', '--detailed', action='store_true', default=False,
                          help='display detailed statistics')
            .add_argument('--use-labels', action='store_true',
                          help='use labels in ranking (DECLINED at the bottom, etc.)')
            .add_argument('-L', '--highlanders', action='store_true',
                          help='display statistics only for highlanders')
            .add_argument('-l', '--label',
                          help='display statistics only for people with label')
            .add_argument('--edition', default='current',
                          help="edition for which we want the stats, e.g. '2010-trento'. "
                               "'all' means all editions 'current' (default) means the"
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

        if opts.label:
            pool = [p for p in pool if opts.label in p.labels]

        self._compute_and_print_stats(pool, opts.detailed)

    def _compute_and_print_stats(self, pool, detailed):
        """ Given a pool of applicants, compute and display some statistics.
        """
        observables = ['born', 'gender', 'nationality', 'affiliation',
                       'position', 'applied', 'napplied', 'open_source',
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
                if var in ('born', 'napplied'):
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
        print('====== Students ======')
        # we want first a list of confirmed with names/nationality/affiliations
        self._wiki_tb_head(('Firstname', 'Lastname', 'Nationality', 'Affiliation'))
        for person in sorted(confirmed, key=operator.attrgetter('name')):
            natflag = '{{:flags:%s'%FLAGS[person.nationality].lower()+'.png}}'
            affflag = '{{:flags:%s'%FLAGS[person.affiliation].lower()+'.png}}'
            self._wiki_tb_row((person.name, person.lastname,
                               natflag+' '+person.nationality,
                               affflag+' '+person.affiliation))

        print('\n\n===== Statistics =====')
        self._wiki_tb_head(('','Applicants', 'Participants'))

        # first collect statistics like we do in the do_stat method (DRY ;))))
        observables = ['born', 'gender', 'nationality', 'affiliation',
                       'position', 'applied', 'napplied', 'open_source',
                       'programming', 'python', 'vcs', 'underrep']
        c_confirmed = {}
        c_applicants = {}
        for var in observables:
            c_confirmed[var] = collections.Counter(getattr(p, var) for p in confirmed)
            c_applicants[var] = collections.Counter(getattr(p, var) for p in applicants)

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

        print('\n\n===Details for Participants===')
        for var in observables:
            self._wiki_tb_head((var.upper(), 'Count'))
            if var in ('born', 'napplied'):
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
        self.modified = True
        self.ranking_done = False

    def do_label(self, args):
        """Mark persons with string labels

        label First Last = LABEL   # add label
        label First Last =         # delete labels
        label First Last           # display labels
        label                      # display all labels
        label LABEL                # display people thus labelled
        """
        applications = self.applications
        if args == '':
            for applicant in applications:
                if applicant.labels:
                    print('{} = {}'.format(applicant.fullname.lower(),
                                           applicant.labels))
            return

        if '=' in args:
            fullname, *labels = [item.strip() for item in args.split('=')
                                 if item is not '']
            if labels:
                applications.add_labels(fullname, labels)
            else:
                applications.clear_labels(fullname)
            self.modified = True
        else:
            display_by_label = any(label in set(args.split())
                                   for label in applications.get_all_labels())
            if display_by_label:
                for label in args.split():
                    count = 0
                    printf('== {} ==', label)
                    for applicant in applications:
                        if label in applicant.labels:
                            printf('{}. {}', count, applicant.fullname.lower())
                            count += 1
                    printf('== {} labelled ==', count)
            else:
                applicant = applications.find_applicant_by_fullname(args)
                labels = applicant.labels
                if labels:
                    printf('{} = {}', args, labels)
                else:
                    printf('{} has no labels', args)

    do_label.completions = _complete_name

    save_options = cmd_completer.PagedArgumentParser('save')\
        .add_argument('filename', nargs='?')

    def do_save(self, args):
        "Save the fruits of thy labour"
        opts = self.save_options.parse_args(args.split())
        self.config.save(opts.filename)
        self.modified = False

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
        applications = self.applications

        _write_file('list_confirmed.csv',
                    applications.filter(label=('CONFIRMED', '-', 'DECLINED')))

        _write_file('list_invite.csv',
                    applications.filter(label=('INVITE', '-', 'DECLINED', 'CONFIRMED')))
        _write_file('list_invite_reminder.csv',
                    applications.filter(label=('INVITE', '-', 'DECLINED', 'CONFIRMED')))
        _write_file('list_overqualified.csv',
                    applications.filter(label=('OVERQUALIFIED', '-', 'CUSTOM-ANSWER')))
        _write_file('list_custom_answer.csv',
                    applications.filter(label=('CUSTOM-ANSWER')))
        # get all INVITESL? labels
        all_labels = self.applications.get_all_labels()
        invitesl = [label for label in all_labels
                    if label.startswith('INVITESL')]
        for i, sl_label in enumerate(invitesl):
            _write_file_samelab(
                'list_same_lab%d.csv'%(i+1),
                applications.filter(label=(sl_label,'-', 'CONFIRMED', 'DECLINED')))
        _write_file('list_shortlist.csv',
                    applications.filter(label=('SHORTLIST', '-', 'DECLINED', 'CONFIRMED', 'INVITE', *invitesl)))
        _write_file('list_rejected.csv',
                    applications.filter(
                        label=('-', 'DECLINED', 'CONFIRMED', 'INVITE', 'SHORTLIST',
                               'OVERQUALIFIED', 'CUSTOM-ANSWER', *invitesl)))
        _write_file('list_declined_invite_nextyear.csv',
                    applications.filter(label=('DECLINED')))

def _write_file(filename, persons):
    header = '$NAME$;$SURNAME$;$EMAIL$'
    if os.path.exists(filename):
        printf("'{}' already exists. We cannot overwrite it!", filename)
        return
    with open(filename, 'w') as f:
        f.write(header + '\n')
        i = -1
        for i, person in enumerate(persons):
            row = ';'.join((person.name, person.lastname, person.email))
            f.write(row + '\n')
    printf("'{}' written with header + {} rows", filename, i + 1)

def _write_file_samelab(filename, persons):
    persons = list(persons)
    if len(persons) == 0:
        printf("No matching persons for '{}'. Check labels!", filename)
    if os.path.exists(filename):
        printf("'{}' already exists. We cannot overwrite it!", filename)
        return
    header = ';'.join('$%dNAME$;$%dSURNAME$'%(d+1,d+1) for d in range(len(persons))) + ';$EMAIL$'
    with open(filename, 'w') as f:
        f.write(header + '\n')
        names = []
        emails = []
        i = -1
        for i, person in enumerate(persons):
            names.extend([person.name, person.lastname])
            emails.append(person.email)
        names = ';'.join(names)
        emails = ','.join(emails)
        f.write(names+';'+emails+'\n')
    printf("'{}' written with header + {} entries", filename, i + 1)

def eval_formula(formula, vars):
    try:
        return eval(formula, vars, {})
    except (NameError, TypeError) as e:
        vars.pop('__builtins__', None)
        msg = 'formula failed: {}\n[{}]\n[{}]'.format(e, formula,
                                                      pprint.pformat(vars))
        raise ValueError(msg)
    else:
        vars.pop('__builtins__', None)

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

KNOWN_GENDER_LABELS = {
    'female'    : 'F',
    'male'      : 'M',
    'other'     : 'O',
    'non-binary': 'O',
    ''          : 'U', # unknown
    'prefer not to say' : 'U'
}
def gender_to_formula_label(label):
    "Convert a gender label from the survey into a single-letter label"
    return KNOWN_GENDER_LABELS[label.lower()]

def categorical_scores(person, categories):
    vars = {}
    for attr, dict in categories.items():
        # Some attributes might not be defined by Person. Let's not define the
        # variable in that case. This will cause the formula evaluation to fail
        # if it refers to one of the undefined attributes.
        try:
            key = getattr(person, attr)
        except AttributeError:
            pass
        else:
            value = get_rating(attr, dict, key)
            vars[attr] = value
    return vars

def rank_person(person, formula, location, categories,
                motivation_scores, minsc, maxsc, labels,
                applied):
    "Apply formula to person and return score"
    vars = categorical_scores(person, categories)

    vars.update(born=int(person.born) if person.born else 0, # if we decide to implement ageism
                gender=gender_to_formula_label(person.gender), # if we decide, …
                                                               # oh we already did
                nonmale=person.nonmale,
                female=person.nonmale, # a compat mapping for old formulas
                applied=applied,
                nationality=person.nationality,
                affiliation=person.affiliation,
                location=location,
                motivation=motivation_scores.mean(),
                email=person.email, # should we discriminate against gmail?
                labels=labels,
                )
    score = eval_formula(formula, vars)
    # we want to round the score, to avoid wrong rankings due to numerical
    # noise. Example: 1.26 and 1.2600000000002 are the same score.
    # Round to 5 digits. That should be above any numerical noise but still
    # below what matters for us.
    score = round(score, 5)
    assert (math.isnan(score) or minsc <= score <= maxsc or labels), \
        (minsc, score, maxsc, vars)
    # labels can cause the score to exceed normal range

    # XXX: Remove scaling until we find a better solution to compare
    #      different formulas
    # scale linearly to SCORE_RANGE/min/max
    #range = max(SCORE_RANGE) - min(SCORE_RANGE)
    #offset = min(SCORE_RANGE)
    #score = (score - minsc) / (maxsc - minsc) * range + offset
    return score

def _yield_values(var, *values):
    for value in values:
        yield var, value

def find_names(formula):
    g = tokenize.tokenize(io.BytesIO(formula.encode('utf-8')).readline)
    return set(tokval for toknum, tokval, _, _, _  in g
                      if toknum == token.NAME and not keyword.iskeyword(tokval))

def find_min_max(formula, location,
                 programming_rating, open_source_rating, python_rating, vcs_rating, underrep_rating,
                 applied):
    # Coordinate with rank_person!
    # Labels are excluded from this list, they add "extra" points.
    # And we would have to test all combinations of labels, which can be slow.
    choices = dict(
        born=(1900, 2012),
        gender=tuple(set(KNOWN_GENDER_LABELS.values())),
        nonmale=(0, 1),
        applied=(0, max(applied)),
        nationality=('Nicaragua', 'Československo', location),
        affiliation=('Československo', 'Nicaragua', location),
        location=(location,),
        motivation=SCORE_RANGE,
        programming=programming_rating.values(),
        open_source=open_source_rating.values(),
        python=python_rating.values(),
        vcs=vcs_rating.values(),
        underrep=underrep_rating.values(),
        labels=())
    needed = list(_yield_values(n, *choices[n]) for n in find_names(formula))
    options = tuple(itertools.product(*needed))
    values = [eval_formula(formula, dict(vars)) for vars in options]
    if not values:
        return float('nan'), float('nan'), {}

    minsc = min(values)
    maxsc = max(values)
    # scorporate in single contributions
    items = collections.OrderedDict()
    for item in formula.split('+'):
        values = [eval_formula(item, dict(vars)) for vars in options]
        max_ = max(values)
        min_ = min(values)
        items[item] = (max_-min_)/(maxsc-minsc)*100
    return minsc, maxsc, items

def wrap_paragraphs(text, prefix=''):
    prefix = '\n' + ' ' * len(prefix)
    paras = text.strip().split('\n\n')
    wrapped = (prefix.join(prefix.join(textwrap.wrap(line.strip()))
                           for line in para.split('\n'))
               for para in paras)
    return ('\n'+prefix).join(wrapped)


grader_options = cmd_completer.ModArgumentParser('grader')\
    .add_argument('-i', '--identity', type=int,
                  choices=IDENTITIES,
                  help='Index of person grading applications')\
    .add_argument('config', type=our_configfile, nargs='?',
                  default=os.path.join(os.getcwd(), 'grader.conf'))\
    .add_argument('applications', type=str, nargs='*',
                  help='''CSV files with application data.
                          The first is current, subsequent are from previous years.
                       ''')

def main():
    logging.basicConfig(level=logging.INFO)

    opts = grader_options.parse_args()
    cmd = Grader(opts.identity, opts.config, opts.applications)

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

    if cmd.modified:
        printff("It seems thy labours' fruits may be going into oblivion...")
        with Umask(0o077):
            tmpfile = tempfile.mkstemp(prefix='grader-', suffix='.conf')[1]
            printff("Saving them to {} instead", tmpfile)
            cmd.do_save(tmpfile)

if __name__ == '__main__':
    sys.exit(main())
