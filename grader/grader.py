import sys
import traceback

import cmd_completer


class Grader(cmd_completer.Cmd_Completer):
    prompt = 'grader> '
    HISTFILE = '~/.grader_history'

    def __init__(self, datafile):
        cmd_completer.Cmd_Completer.__init__(self, histfile=self.HISTFILE)

grader_options = cmd_completer.ModArgumentParser('grader')\
    .add_argument('applications', type=open,
                  help='CSV file with application data')

def main(*args):
    cmd = Grader(grader_options.parse_args(args))

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
