#!/usr/bin/python3
import sys
import os
import math
import numbers
import traceback
import csv
import collections
import textwrap
import pprint
import configfile
import itertools
import logging
import tempfile
import contextlib
import operator

import cmd_completer
import vector

float_nan = float("nan")

def printf(fmt, *args, **kwargs):
    print(fmt.format(*args, **kwargs))

# like printf above, but this time with explicit flush.
# it should be used everytime you want the strings
# to be print immediately and not only at the end of
# the command
def printff(fmt, *args, **kwargs):
    print(fmt.format(*args, **kwargs))
    cmd_completer.PAGER.flush()

@contextlib.contextmanager
def Umask(umask):
    old = os.umask(umask)
    try:
        yield
    finally:
        os.umask(old)


DUMP_FMT = '''\
name: {p.name} {p.lastname} {labels}<{p.email}>
born: {p.nationality} {p.born}
gender: {p.gender}
institute: {p.institute}
group: {p.group}
affiliation: {p.affiliation}
position: {p.position}{position_other}
appl.prev.: {p.applied} {p.napplied}
programming: {p.programming}{programming_description} [{programming_score}]
python: {p.python} [{python_score}]
open source: {p.open_source}{open_source_description} [{open_source_score}]
cv: {cv} [{cv_scores}]
motivation: {motivation} [{motivation_scores}]
rank: {p.rank} {p.score} {p.highlander}
'''

_RANK_FMT_LONG = ('{: 4} {p.rank: 4} {labels:{labels_width}} {p.score:6.3f}'
                 ' {p.fullname:{fullname_width}} {email:{email_width}}'
                 ' {p.institute:{institute_width}} / {p.group:{group_width}}')
_RANK_FMT_SHORT = ('{: 4} {p.rank: 4} {labels:{labels_width}} {p.score:6.3f}'
                 ' {p.fullname:{fullname_width}} {email:{email_width}}')
_RANK_FMT_DETAILED = ('{: 4} {p.rank: 4} {labels:{labels_width}} {p.score:6.3f}'
                 ' [{motivation_scores}] [appl: {p.applied} {p.napplied}]'
                 ' [prog: {programming_score}] [python: {python_score}]'
                 ' [os: {open_source_score}]'
                 ' {p.fullname:{fullname_width}} {email:{email_width}}')
RANK_FORMATS = {'short': _RANK_FMT_SHORT,
                'long': _RANK_FMT_LONG,
                'detailed': _RANK_FMT_DETAILED,
                }

SCORE_RANGE = (-1, 0, 1)

IDENTITIES = (0, 1)

HOST_COUNTRY = 'Germany'

DEFAULT_ACCEPT_COUNT = 30

section_name = '{}_score-{}'.format

COLOR = {
    'default': '\x1b[0m',
    'grey'   : '\x1b[1;30m',
    'red'    : '\x1b[1;31m',
    'green'  : '\x1b[1;32m',
    'yellow' : '\x1b[1;33m',
    'blue'   : '\x1b[1;34m',
    'violet' : '\x1b[1;35m',
    'cyan'   : '\x1b[1;36m',
    'white'  : '\x1b[1;37m',
    }

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

    def _init_applications(self, applications):
        section = self.config['application_lists']
        if applications:
            section.clear()
            for i,file in zip('abcdefghijkl', applications):
                section[i] = file.name
        else:
            applications = [open_no_newlines(filename) for filename
                            in self.config['application_lists'].values()]
        self.applications = self.csv_file(applications[0])
        self.applications_old = [self.csv_file(list)
                                 for list in applications[1:]]

    @classmethod
    def Person(cls, names):
        class Person(collections.namedtuple('Person', names)):
            def __init__(self, *args, **kwargs):
                super().__init__()#*args, **kwargs)
                self.score = None
                self.rank = None
                self.highlander = None
                self.napplied = 0
            @property
            def fullname(self):
                return '{p.name} {p.lastname}'.format(p=self)
            @property
            def female(self):
                return self.gender == 'Female'
        return Person

    @property
    def application_fields(self):
        section = self.config['fields']
        if len(list(section.keys())) == 0:
            def add(k, v):
                section[k] = list_of_equivs(v)
            for f in """id completed last_page_seen start_language
                        date_last_action date_started
                        ip_address referrer_url
                        gender
                        position institute group nationality
                        python
                        name email
                        token""".split():
                add(f, f.replace('_', ' '))
            add('affiliation', "Country of Affiliation")
            add('position_other', "[Other] Position")
            add('applied', "Did you already apply")
            add('programming', "estimate your programming skills")
            add('programming_description', "programming experience")
            add('open_source', "exposure to open-source")
            add('open_source_description', "description of your contrib")
            add('motivation', "appropriate course for your skill profile")
            add('cv', "curriculum vitae")
            add('lastname', "Last name")
            add('born', "Year of birth")
        return section

    @vector.vectorize
    def _fields(self, header):
        failed = None
        for name in header:
            try:
                yield self._field_master(name)
            except KeyError as e:
                printf("unknown field: '{}'".format(name))
                failed = e
        if failed:
            pprint.pprint(list(self.application_fields.items()))
            raise failed

    def _field_master(self, description):
        """Return the name of a field for this description. Must be defined.

        The double dance is because we want to map:
        - position <=> position,
        - [other] position <=> position_other,
        - curriculum vitae <=> Please type in a short curriculum vitae...
        """
        for key, values in self.application_fields.items():
            if description.lower() == key.lower():
                return key
        candidates = {}
        for key, values in self.application_fields.items():
            for spelling in values:
                if spelling.lower() in description.lower():
                    candidates[spelling] = key
        if candidates:
            ans = candidates[sorted(candidates.keys(), key=len)[-1]]
            return ans
        raise KeyError(description)

    def _applied(self, person, warn=True):
        "Return the number of times a person applied"
        declared = int(person.applied[0] not in 'nN')
        found = 0
        for old in self.applications_old:
            found += (person.fullname in old.fullname or
                      person.email in old.email)
        if warn and found and not declared:
            printf('warning: person found in list says not applied prev.: {}',
                   person.fullname)
        if warn and declared and not found:
            printf('warning: person applied prev. not found on lists: {}',
                   person.fullname)
        person.napplied = max(declared, found)
        return person.napplied

    def _applied_range(self):
        s = set(self._applied(p, warn=False) for p in self.applications)
        return sorted(s)

    @vector.vectorize
    def csv_file(self, file):
        printf("loading '{}'", file.name)
        reader = csv.reader(file)
        header = next(reader)
        fields = self._fields(header)
        tuple_factory = self.Person(fields)
        assert len(header) == len(tuple_factory._fields)
        while True:
            yield tuple_factory(*next(reader))

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

    def _complete_name(self, prefix):
        """Return a list of dictionaries {name -> [last-name+]}

        Name or last-name must start with prefix.
        """
        completions = collections.defaultdict(set)
        for p in self.applications:
            if p.name.startswith(prefix) or p.lastname.startswith(prefix):
                completions[p.name].add(p.lastname)
        return completions

    identity_options = cmd_completer.ModArgumentParser('identity')\
        .add_argument('identity', type=int, choices=IDENTITIES,
                      help='become this identity')

    def do_identity(self, args):
        "Switch identity"
        opts = self.identity_options.parse_args(args.split())
        self.identity = opts.identity

    exception_options = cmd_completer.ModArgumentParser('exception')\
        .add_argument('exception',
                      help='the exception type to be raised')

    def do_exception(self, args):
        "Fake command to test exception capturing"
        opts = self.exception_options.parse_args(args.split())
        raise getattr(__builtins__, opts.exception[0])

    dump_options = cmd_completer.ModArgumentParser('dump')\
        .add_argument('-d', '--detailed', action='store_const',
                      dest='format', const='long', default='short',
                      help='do not truncate free texts')\
        .add_argument('-s', '--sorted', action='store_true',
                      help='print applications sorted by rank')\
        .add_argument('-L', '--highlanders', action='store_const',
                      dest='highlanders', const=True, default=False,
                      help='print applications only for highlanders')\
        .add_argument('-l', '--label', type=str,
                      dest='label', nargs=1,
                      help='print applications only for people with label')\
        .add_argument('persons', nargs='*',
                      help='name fragments of people do display')

    def do_dump(self, args):
        "Print information about applications"
        opts = self.dump_options.parse_args(args.split())
        if opts.persons:
            persons = (p for p in self.applications
                       if any(arg in p.fullname for arg in opts.persons))
        elif opts.label:
            persons = tuple(self._filter(opts.label[0]))
        else:
            persons = self.applications
        if opts.highlanders:
            persons = (p for p in persons if p.highlander)
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
        elif format == 'long':
            pd = wrap_paragraphs(p.programming_description) + '\n'
            osd = wrap_paragraphs(p.open_source_description) + '\n'
            cv = wrap_paragraphs(p.cv) + '\n'
            motivation = wrap_paragraphs(p.motivation) + '\n'
        else:
            raise KeyError("unknown format '{}'".format(format))
        programming_description = ('\nprogramming: {}'.format(pd)
                                   if p.programming_description else '')
        open_source_description = ('\nopen source: {}'.format(osd)
                                   if p.open_source_description else '')
        labels = self._labels(p.fullname)
        if labels:
            labels = '[{}] '.format(labels)
        printf(DUMP_FMT,
               p=p,
               position_other=position_other,
               programming_description=programming_description,
               open_source_description=open_source_description,
               programming_score=\
                   get_rating('programming', self.programming_rating,
                              p.programming, '-'),
               open_source_score=\
                   get_rating('open_source', self.open_source_rating,
                              p.open_source, '-'),
               python_score=\
                   get_rating('python', self.python_rating, p.python, '-'),
               cv=cv,
               motivation=motivation,
               cv_scores=self._gradings(p, 'cv'),
               motivation_scores=self._gradings(p, 'motivation'),
               labels=labels,
               )

    def do_grep(self, args):
        "Look for string in applications"
        if args.split()[0] == '-l':
            format = 'long'
            args = args[args.index('-l')+2:].lstrip()
        else:
            format='short'

        self._dump((p for p in self.applications
                    if args in str(p)), format=format)

    grade_options = cmd_completer.ModArgumentParser('grade')\
        .add_argument('what', choices=['motivation', 'cv', 'formula'],
                      help='what to grade | set formula')\
        .add_argument('-g', '--graded', action='store_true',
                      help='grade already graded too')\
        .add_argument('person', nargs='*')

    @set_completions('formula',
                     motivation=_complete_name,
                     cv=_complete_name)
    def do_grade(self, arg):
        """Assign points to motivation or CV statements or set formula

        Formula is set with:
          grade formula ...
        where ... is a python expression using the following variables:
          born: int,
          gender: 'M' or 'F',
          female: 0 or 1,
          nationality: str,
          affiliation: str,
          motivation: float,
          cv: float,
          programming: float,
          open_source: float,
          applied: 0 or 1 or 2 or ...,
          python: float,
          labels: list of str.
        """
        if self.identity is None:
            raise ValueError('cannot do grading because identity was not set')

        opts = self.grade_options.parse_args(arg.split())
        if opts.graded and opts.person:
            raise ValueError('cannot use --graded option with explicit name')

        if opts.what == 'formula':
            if opts.person:
                self.formula = ' '.join(opts.person)
                self.modified = True
            minsc, maxsc, contr = find_min_max(self.formula,
                                               self.programming_rating,
                                               self.open_source_rating,
                                               self.python_rating,
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

        printff('Doing grading for identity {}', self.identity)
        printff('Press ^C or ^D to stop')
        fullname = ' '.join(opts.person)

        todo = [p for p in self.applications
                if (p.fullname == fullname if fullname
                    else
                    opts.graded or
                    self._get_grading(p, opts.what) is None)]
        done_already = len(self.applications) - len(todo)
        for num, person in enumerate(todo):
            printff('{:.2f}% done, {} left to go',
                   100*(num+done_already)/len(self.applications),
                   len(todo)-num)
            if not self._grade(person, opts.what):
                break

    RATING_CATEGORIES = ['programming', 'open_source', 'python']

    rate_options = cmd_completer.ModArgumentParser('rate')\
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

    def _get_grading(self, person, what):
        section = self.config[section_name(what, self.identity)]
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

    def _grade(self, person, what):
        assert what in {'motivation', 'cv'}, what
        text = getattr(person, what)
        old_score = self._get_grading(person, what)
        default = old_score if old_score is not None else ''
        printff('{line}\n{}\n{line}', wrap_paragraphs(text), line='-'*70)
        printff('Old score was {}', old_score)
        while True:
            prompt = 'Your choice {} [{}]? '.format(SCORE_RANGE, default)
            try:
                choice = input(prompt)
            except EOFError:
                print()
                return False
            if choice == 's':
                printff('person skipped')
                return True
            elif choice == 'd':
                printff('showing person on request')
                self._dumpone(person, format='long')
                continue
            elif choice == '':
                choice = default
            if choice == '+':
                choice = SCORE_RANGE[-1]
            elif choice == '-':
                choice = SCORE_RANGE[0]
            try:
                choice = int(choice)
                if choice not in SCORE_RANGE:
                    raise ValueError('illegal value: {}'.format(choice))
            except ValueError as e:
                printff(str(e))
            else:
                break
        if choice != default:
            self._set_grading(person, what, choice)
        return True

    def _assign_rankings(self):
        "Order applications by rank"
        if self.formula is None:
            raise ValueError('formula not set yet')

        if self.ranking_done:
            return
        else:
            self.ranking_done = True
        minsc, maxsc, contr = find_min_max(self.formula,
                                           self.programming_rating,
                                           self.open_source_rating,
                                           self.python_rating,
                                           self._applied_range())

        for person in self.applications:
            person.score = rank_person(person, self.formula,
                                       self.programming_rating,
                                       self.open_source_rating,
                                       self.python_rating,
                                       self._gradings(person, 'motivation'),
                                       self._gradings(person, 'cv'),
                                       minsc, maxsc,
                                       self._labels(person.fullname),
                                       self._applied(person))
        ranked = sorted(self.applications, key=lambda p: p.score, reverse=True)

        sort = []
        # put VIPS at the beginning of the list, and set the rank already
        for person in ranked:
            if 'VIP' in self._labels(person.fullname):
                person.rank = 0
                sort.insert(0, person)
            else:
                sort.append(person)
        # rank fairly now
        for idx, person in enumerate(sort):
            if person.rank is not None:
                continue
            # this is in case we have no VIPs
            if idx == 0:
                person.rank = 1
                continue
            # main logic
            prev_rank = sort[idx-1].rank
            if person.score == sort[idx-1].score:
                person.rank = prev_rank
            else:
                person.rank = prev_rank + 1

        # now choose the highlanders:
        for i, p in enumerate(sort):
            p.highlander = i < self.accept_count
            # check if we have other people with the same ranking
            if not p.highlander:
                prev = sort[i-1]
                if prev.highlander and (prev.rank == p.rank):
                    p.highlander = True

        ## for person in ranked:
        ##     # VIPs get in front of the list
        ##     if 'VIP' in self._labels(person.fullname):
        ##         person.rank = 1
        ##         continue
        ##     if rank == self.accept_count:
        ##         labs = {}
        ##     group = self._equiv_master(person.group)
        ##     institute = self._equiv_master(person.institute)
        ##     lab = institute + ' | ' + group
        ##     if lab not in labs:
        ##         labs[lab] = rank
        ##         rank += 1
        ##     person.rank = labs[lab]

    def _ranked(self, applications=None):
        if applications is None:
            applications = self.applications

        ranked = sorted(applications, key=lambda p: p.rank)
        return vector.vector(ranked)

    def _equiv_master(self, variant):
        "Return the key for equiv canocalization"
        for key, values in self.config['equivs'].items():
            if (variant.lower() == key.lower() or
                variant.lower() in (spelling.lower() for spelling in values)):
                return key
        return variant.strip()

    rank_options = cmd_completer.ModArgumentParser('rank')\
        .add_argument('-s', '--short', action='store_const',
                      dest='format', const='short', default='long',
                      help='show only names and emails')\
        .add_argument('--format',
                      dest='format', choices=('long', 'short', 'detailed'),
                      help='show only names and emails')

    def do_rank(self, args):
        "Print list of people sorted by ranking"
        opts = self.rank_options.parse_args(args.split())
        self._assign_rankings()
        ranked = self._ranked()
        fullname_width = max(len(field) for field in ranked.fullname)
        email_width = max(len(field) for field in ranked.email)
        institute_width = min(max(len(field) for field in ranked.institute), 20)
        group_width = min(max(len(field) for field in ranked.group), 20)
        labels_width = max(len(str(self._labels(field)))
                           for field in ranked.fullname) or 1

        fmt = RANK_FORMATS[opts.format]
        prev_highlander = True
        print(COLOR['grey']+'-' * 70+COLOR['default'])
        for pos, person in enumerate(ranked):
            if prev_highlander and not person.highlander:
                print(COLOR['grey']+'-' * 70+COLOR['default'])
            prev_highlander = person.highlander
            labels = self._labels(person.fullname)
            if 'CONFIRMED' in labels:
                line_color = COLOR['default']
            elif 'DECLINED' in labels:
                line_color = COLOR['red']
            elif 'INVITE' in labels and 'CONFIRMED' not in labels:
                line_color = COLOR['yellow']
            else:
                line_color = COLOR['grey']
            printf(line_color+fmt+COLOR['default'], pos+1, p=person,
                   email='<{}>'.format(person.email),
                   fullname_width=fullname_width, email_width=email_width,
                   institute_width=institute_width, group_width=group_width,
                   labels=labels,
                   labels_width=labels_width,
                   motivation_scores=self._gradings(person, 'motivation'),
                   programming_score=\
                       get_rating('programming', self.programming_rating,
                                  person.programming, '-'),
                   open_source_score=\
                       get_rating('open_source', self.open_source_rating,
                                  person.open_source, '-'),
                   python_score=\
                       get_rating('python', self.python_rating,
                                  person.python, '-'),
                   )

    stat_options = cmd_completer.ModArgumentParser('stat')\
                   .add_argument('-d', '--detailed', action='store_const',
                                 dest='detailed', const=True, default=False,
                                 help='display detailed statistics')\
                   .add_argument('-L', '--highlanders', action='store_const',
                                 dest='highlanders', const=True, default=False,
                                 help='display statistics only for highlanders')\
                   .add_argument('-l', '--label', type=str,
                                 dest='label', nargs=1,
                                 help='display statistics only for people with label')

    def do_stat(self, args):
        "Display statistics"
        opts = self.stat_options.parse_args(args.split())
        if opts.highlanders:
            ranked = self._ranked()
            self._assign_rankings()
            pool = [person for person in ranked if person.highlander]
        else:
            pool = self.applications
        if opts.label:
            pool = tuple(self._filter(opts.label[0]))
            
        observables = ['born', 'female', 'nationality', 'affiliation',
                       'position', 'applied', 'napplied', 'open_source',
                       'programming', 'python']
        counter = {}
        for var in observables:
            counter[var] = collections.Counter(getattr(p, var) for p in pool)

        length = {var:len(counter[var]) for var in observables}
        applicants = len(pool)
        FMT_STAT = '{:<24.24} = {:>3d}'
        FMT_STAP = FMT_STAT + ' ({:4.1f}%)'
        printf(FMT_STAT, 'Pool', applicants)
        printf(FMT_STAT, 'Nationalities', length['nationality'])
        printf(FMT_STAT, 'Countries of affiliation', length['affiliation'])
        printf(FMT_STAP, 'Females', counter['female'][True],
               counter['female'][True]/applicants*100)
        for pos in counter['position'].most_common():
            printf(FMT_STAP, pos[0], pos[1], pos[1]/applicants*100)
        if opts.detailed:
            for var in observables:
                print('--\n'+var.upper())
                for n in sorted(counter[var].items(),
                                key=operator.itemgetter(1), reverse=True):
                    printf(FMT_STAP, str(n[0]), n[1], n[1]/applicants*100)
       
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

    def _labels(self, fullname):
        return self.config['labels'].get(fullname, list_of_str())

    def _get_all_labels(self):
        labels = set()
        for l in self.config['labels'].values():
            labels.update(l)
        return labels

    def do_label(self, args):
        """Mark persons with string labels

        label First Last = LABEL   # add label
        label First Last =         # delete labels
        label First Last           # display labels
        label                      # display all labels
        label LABEL                # display people thus labelled
        """
        section = self.config['labels']
        if args == '':
            for key, value in section.items():
                printf('{} = {}', key, value)
            return

        if '=' in args:
            fullname, *labels = [item.strip() for item in args.split('=')
                                 if item is not '']
            if labels:
                saved = self._labels(fullname)
                saved.extend(labels)
                section[fullname] = saved
            else:
                section.clear(fullname)
            self.modified = True
        else:
            display_by_label = any(label in set(args.split())
                                   for group in section.values()
                                   for label in group)
            if display_by_label:
                for label in args.split():
                    count = 0
                    printf('== {} ==', label)
                    for key, value in section.items():
                        if label in value:
                            printf('{}. {}', count, key)
                            count += 1
                    printf('== {} labelled ==', count)
            else:
                printf('{} = {}', args, section[args])

    do_label.completions = _complete_name

    save_options = cmd_completer.ModArgumentParser('save')\
        .add_argument('filename', nargs='?')

    def do_save(self, args):
        "Save the fruits of thy labour"
        opts = self.save_options.parse_args(args.split())
        self.config.save(opts.filename)
        self.modified = False

    def _filter(self, *accept_dash_deny):
        """Find people who have all labels in accept and none from deny.

        Arguments are split into the part before '-', and after. The
        first becomes a list of labels that must be present, and the
        second becomes a list of labels which cannot be present.

        self._filter('XXX') --> people who have 'XXX'
        self._filter('XXX', 'YYY') --> people who have both
        self._filter('XXX', 'YYY', '-', ZZZ') --> people who have both
           'XXX' and 'YYY', but don't have 'ZZZ'
        self._filter('XXX', 'YYY', '-', ZZZ', 'ŻŻŻ') --> people who have
           both 'XXX' and 'YYY', but neither 'ZZZ' nor 'ŻŻŻ'.
        """
        labels = iter(accept_dash_deny)
        accept = frozenset(itertools.takewhile(lambda x: x!='-', labels))
        deny = frozenset(labels)
        for p in self.applications:
            labels = set(self._labels(p.fullname))
            if not (accept - labels) and not (labels & deny):
                yield p

    def do_write(self, args):
        """Write lists of mailing ricipients

        Labels have the following precedence:
        - DECLINE - person cancelled, let's forget about them
        - CONFIRMED - person is coming, let's forget about them for now
        - INVITE - person to invite
        - SHORTLIST - person to potentially invite
        - REJECTED - the rest
        """
        if args != '':
            raise ValueError('no args please')
        #ranked = self._ranking()
        #printf('accepting {}', self.accept_count)
        #count = collections.Counter(ranked.rank)

        _write_file('applications_confirmed.csv',
                    self._filter('CONFIRMED', '-', 'DECLINED'))

        _write_file('applications_invite.csv',
                    self._filter('INVITE', '-', 'DECLINED', 'CONFIRMED'))
        #_write_file('applications_same_lab.csv',
        #            (person for person in ranked if person.highlander and
        #             count[person.rank] != 1))
        _write_file('applications_shortlist.csv',
                    self._filter('SHORTLIST', '-', 'DECLINED', 'CONFIRMED', 'INVITE'))
        _write_file('applications_rejected.csv',
                    self._filter('-', 'DECLINED', 'CONFIRMED', 'INVITE', 'SHORTLIST'))
        _write_file('applications_declined.csv',
                    self._filter('DECLINED'))

def _write_file(filename, persons):
    header = '$NAME$;$SURNAME$;$EMAIL$'
    with open(filename, 'w') as f:
        f.write(header + '\n')
        i = -1
        for i, person in enumerate(persons):
            row = ';'.join((person.name, person.lastname, person.email))
            f.write(row + '\n')
    printf("'{}' written with header + {} rows", filename, i+1)

def eval_formula(formula, vars):
    try:
        return eval(formula, vars, {})
    except (NameError, TypeError) as e:
        vars.pop('__builtins__', None)
        msg = 'formula failed: {}\n[{}]\n[{}]'.format(e, formula,
                                                      pprint.pformat(vars))
        raise ValueError(msg)

class MissingRating(KeyError):
    def __str__(self):
        return '{} not rated for {}'.format(*self.args)
    @property
    def key(self):
        return self.args[1]

def get_rating(name, dict, key, fallback=None):
    """Retrieve rating.

    Explanation in () or after / is ignored in the key.

    Throws ValueError is rating is not present.
    """
    key = key.partition('(')[0].partition('/')[0].strip()
    try:
        return dict[key]
    except KeyError:
        if fallback is None:
            raise MissingRating(name, key)
            # raise ... from None, when implemented!
        else:
            return fallback

class list_of_float(list):
    def __str__(self):
        return ', '.join(str(item) if item is not None else '-'
                         for item in self)

    def mean(self):
        valid = [arg for arg in self if arg is not None]
        if not valid:
            return float_nan
        return sum(valid) / len(valid)

class list_of_str(list):
    def __init__(self, arg=None):
        equivs = ((item.strip() for item in arg.split(','))
                  if arg is not None else ())
        super().__init__(equivs)

    def __str__(self):
        return ', '.join(self)

def rank_person(person, formula,
                programming_rating, open_source_rating, python_rating,
                motivation_scores, cv_scores, minsc, maxsc, labels,
                applied):
    "Apply formula to person and return score"
    vars = {}
    for attr, dict in zip(('programming', 'open_source', 'python'),
                          (programming_rating, open_source_rating, python_rating)):
        key = getattr(person, attr)
        value = get_rating(attr, dict, key)
        vars[attr] = value
    vars.update(born=int(person.born), # if we decide to implement ageism
                gender=person.gender, # if we decide, ...
                                      # oh we already did
                female=person.female,
                applied=applied,
                nationality=person.nationality,
                affiliation=person.affiliation,
                motivation=motivation_scores.mean(),
                cv=cv_scores.mean(),
                email=person.email, # should we discriminate against gmail?
                labels=labels,
                )
    score = eval_formula(formula, vars)
    assert (math.isnan(score) or minsc <= score <= maxsc or labels), \
        (minsc, score, maxsc)
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

def find_min_max(formula,
                 programming_rating, open_source_rating, python_rating,
                 applied):
    # Coordinate with rank_person!
    # Labels are excluded from this list, they add "extra" points.
    # And we would have to test all combinations of labels, which can be slow.
    options = tuple(itertools.product(
        _yield_values('born', 1900, 2012),
        _yield_values('gender', 'M', 'F'),
        _yield_values('female', 0, 1),
        _yield_values('nationality', 'Nicaragua', HOST_COUNTRY),
        _yield_values('affiliation', 'Nicaragua', HOST_COUNTRY),
        _yield_values('motivation', *SCORE_RANGE),
        _yield_values('cv', *SCORE_RANGE),
        _yield_values('programming', *programming_rating.values()),
        _yield_values('open_source', *open_source_rating.values()),
        _yield_values('applied', 0, max(applied)),
        _yield_values('python', *python_rating.values()),
        _yield_values('labels', list_of_str()),
        ))
    values = [eval_formula(formula, dict(vars)) for vars in options]
    if not values:
        return float_nan, float_nan, {}

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

def wrap_paragraphs(text):
    paras = text.strip().split('\n\n')
    wrapped = ('\n'.join(textwrap.wrap(para)) for para in paras)
    return '\n\n'.join(wrapped)

class list_of_equivs(list):
    def __init__(self, arg=None):
        equivs = ((item.strip() for item in arg.split('='))
                  if arg is not None else ())
        super().__init__(equivs)

    def __str__(self):
        return ' = '.join(self)

def our_configfile(filename):
    kw = {section_name(what, ident):float
          for what in ('motivation', 'cv')
          for ident in IDENTITIES}
    return configfile.ConfigFile(filename,
                                 application_lists=str,
                                 programming_rating=float,
                                 open_source_rating=float,
                                 python_rating=float,
                                 formula=str,
                                 equivs=list_of_equivs,
                                 labels=list_of_str,
                                 fields=list_of_equivs,
                                 **kw)

def open_no_newlines(filename):
    return open(filename, newline='')

grader_options = cmd_completer.ModArgumentParser('grader')\
    .add_argument('-i', '--identity', type=int,
                  choices=IDENTITIES,
                  help='Index of person grading applications')\
    .add_argument('config', type=our_configfile, nargs='?',
                  default=os.path.join(os.getcwd(), 'grader.conf'))\
    .add_argument('applications', type=open_no_newlines, nargs='*',
                  help='''CSV files with application data.
                          The first is current, subsequent are from previous years.
                       ''')

def main(argv0, *args):
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
    sys.exit(main(*sys.argv))
