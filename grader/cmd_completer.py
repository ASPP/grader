import sys
import os
import atexit
import readline
import cmd
import argparse
import re

import logging
log = logging.getLogger('cmd_completer')

class Cmd_Completer(cmd.Cmd):
    def __init__(self, histfile=None):
        cmd.Cmd.__init__(self)

        if histfile is None:
            return
        histfile = os.path.expanduser(histfile)

        try:
            readline.read_history_file(histfile)
            log.info('read history')
        except IOError:
            pass
        atexit.register(readline.write_history_file, histfile)

    @staticmethod
    def set_completions(*commands, **completions):
        assert not (set(commands) & set(completions))
        completions.update({command:() for command in commands})
        def decorate(f):
            f.completions = completions
            return f
        return decorate

    def traverse(self, words):
        log.debug('traverse %s', words)
        try:
            func = getattr(self, 'do_'+words[0])
            where = func.completions
        except AttributeError:
            return None

        for word in words[1:-1]:
            if not isinstance(where, dict):
                return None
            where = where[word]

        return ['%s ' % word
                for word in where if str(word).startswith(words[-1])]

    def completedefault(self, text, line, begidx, endidx):
        words = line[:endidx].rstrip().split()
        if not words or line[-1] == ' ':
            words.append('')
        try:
            return self.traverse(words)
        except KeyError:
            pass
        except Exception:
            log.exception()

    def precmd(self, line):
        """Split line on colons, and return the first part.

        The rest is stored in the cmdqueue."""
        cmd, _, rest = line.partition(';')
        if rest:
            self.cmdqueue.insert(0, rest)
        return cmd

    def do_EOF(self, arg):
        log.info('***bye***')
        return True

    def do_py(self, arg):
        try:
            exec(arg, sys.modules['__main__'].__dict__)
        except Exception as e:
            log.error(e)

    def do_shell(self, arg):
        os.system(arg)

    def emptyline(self):
        pass

    def completenames(self, text, *ignored):
        dotext = 'do_' + text
        return [a[3:] + ' '
                for a in self.get_names() if a.startswith(dotext)]

class ModArgumentParser(argparse.ArgumentParser):
    def exit(self, status=0, message=None):
        if message:
            print(message)
        raise KeyboardInterrupt

    def add_argument(self, *args, **kwargs):
        super(ModArgumentParser, self).add_argument(*args, **kwargs)
        return self

class InputFile:
    COMMENT_OR_EMPTY_RE = re.compile('\s* (?: [#] | $ )', re.X)

    def __init__(self, input):
        self.file = input

    def __iter__(self):
        return self

    def __next__(self):
        while True:
            line = next(self.file)
            if not self.COMMENT_OR_EMPTY_RE.match(line):
                return line
