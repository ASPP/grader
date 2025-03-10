import argparse
import atexit
import cmd
import contextlib
import logging
import io
import os
import pydoc
import readline
import re
import shutil
import sys
import traceback


log = logging.getLogger('cmd_completer')


class PagedStdOut(io.StringIO):
    "Page stdout if needed"
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.buffer = []
        self.pager = pydoc.getpager()
        self.stdout_write = sys.stdout.write
        self.stderr_write = sys.stderr.write
        sys.stdout.write = self.write
        sys.stderr.write = self.direct_write
        if 'LESS' not in os.environ:
            os.environ['LESS'] = '-FSRX'
        global PAGER
        PAGER = self

    def write(self, s):
        # do not really write, just cumulates input
        self.buffer.append(s)

    def direct_write(self, s):
        # write directly, for example for stderr stream,
        self.write(s)
        # add a newline if not there
        if s[-1] != '\n':
            self.write('\n')
        self.flush()

    def flush(self):
        height, width = shutil.get_terminal_size()
        buffer = ''.join(self.buffer)
        sys.stdout.write = self.stdout_write
        sys.stderr.write = self.stderr_write
        if buffer.count('\n') >= height:
            self.pager(buffer)
        else:
            sys.stdout.write(buffer)
        self.buffer = []


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
            if callable(where):
                try:
                    where = where(self, word)
                    log.debug('callable replaced with %s', where)
                except Exception as e:
                    log.exception('callable %s', where, e)
            if not isinstance(where, dict):
                return None
            where = where[word]

        log.debug('where bef=%s', where)
        special = False
        if callable(where):
            try:
                where = where(self, words[-1])
                log.debug('where aft=%s', where)
                special = True
            except Exception as e:
                log.exception('where aft', e)

        log.debug('filtering %s with %s', where, words[-1])
        ans = ['%s ' % word for word in where
               if str(word).startswith(words[-1]) or special]
        log.debug('filtered down to %s', ans)
        return ans

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
        self.page_stdout = PagedStdOut()
        return cmd

    def postcmd(self, stop, line):
        self.page_stdout.flush()
        return stop

    def do_EOF(self, arg):
        "Quit"
        log.info('***bye***')
        return True

    do_exit = do_EOF

    do_quit = do_EOF

    def do_py(self, arg):
        "Execute python statements"
        try:
            ans = eval(arg, self.__dict__)
            if ans is not None:
                print(ans)
        except Exception as e:
            log.error(e)

    def do_loadpy(self, arg):
        "Load code snippet from file"
        with open(arg,'rt') as fh:
            # redirecting stdout to stderr is needed
            # to support flushing the I/O stream in scripts
            with contextlib.redirect_stdout(sys.stderr):
                try:
                    exec(fh.read(), self.__dict__)
                except Exception as e:
                    traceback.print_exc(file=sys.stdout)

    def do_shell(self, arg):
        "Execute shell statements"
        os.system(arg)

    def emptyline(self):
        pass

    def completenames(self, text, *ignored):
        dotext = 'do_' + text
        return [a[3:] + ' '
                for a in self.get_names() if a.startswith(dotext)]

class ModArgumentParser(argparse.ArgumentParser):
    def add_argument(self, *args, **kwargs):
        super(ModArgumentParser, self).add_argument(*args, **kwargs)
        return self

class PagedArgumentParser(ModArgumentParser):
    def exit(self, status=0, message=None):
        if message:
            print(message)
        raise KeyboardInterrupt

    def _print_message(self, message, file=None):
        PAGER.direct_write(message)

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
