import pathlib
import sys

import rich
from rich import print

from . import cmd_completer
from .applications import Applications

class Grader(cmd_completer.Cmd_Completer):
    #prompt = "[green]grader[/green][yellow]>[/yellow] "
    prompt = "grader2> "
    set_completions = cmd_completer.Cmd_Completer.set_completions

    def __init__(self, identity, csv_file, history_file=None):
        super().__init__(histfile=history_file)
        self.applications = Applications(csv_file=csv_file)
        self.identity = None
        if identity is not None:
            self.do_identity(identity)
        self.archive = []
        for path in sorted(csv_file.parent.glob('*/applications.csv'), reverse=True):
            # years before 2012 are to be treated less strictly
            relaxed = any(f'{year}-' in str(path) for year in range(2009,2012))
            old = Applications(csv_file=path, relaxed=relaxed)
            self.archive.append(old)

        for person in self.applications:
            person.set_n_applied(self.archive)


    identity_options = (
        cmd_completer.PagedArgumentParser('identity')
        .add_argument('identity', type=str, help='become this identity')
        )
    def do_identity(self, args):
        "Switch identity"
        opts = self.identity_options.parse_args(args.split())
        self.identity = opts.identity
        numerical_identities = list(self.applications.ini['identities'].keys())
        nominal_identities = list(self.applications.ini['identities'].values())
        if self.identity not in numerical_identities+nominal_identities:
            raise ValueError(f'"{self.identity}" is not a registered identity. Add it '
                             f'to {self.applications.ini.filename}')

grader_options = (
    cmd_completer.ModArgumentParser('grader')
    .add_argument('-i', '--identity', type=str,
                  help='Name of person grading applications')
    .add_argument('--history-file', type=pathlib.Path,
                  default=pathlib.Path('~/.grader_history').expanduser(),
                  help='File to record typed in commands')
    )

def main():
    opts = grader_options.parse_args()

    cmd = Grader(
        identity=opts.identity,
        csv_file=pathlib.Path('applications.csv'),
        history_file=opts.history_file,
    )

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
