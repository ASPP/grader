# -*- coding: utf-8 -*-
"""
grader: a Python module and command-line utility to grade applications.
"""
import os

# current dir
CWD = os.path.abspath(os.path.dirname(__file__))

__name__ =        'grader'
__description__ = 'a Python module and command-line utility to grade applications'
__version__ =     '0.1'
__url__ =         'https://github.com/ASPP/grader'
__author__ =      'grader contributor'
__license__ =     'GPLv3+'


def revision():
    # get the git SHA if we are in a git repo (only useful for devs)
    import subprocess

    # try two options for getting the git revision
    # - nice version with tags
    # - plain SHA
    for cmd in ('git describe --tags --dirty=+'), ('git rev-parse HEAD'):
        try:
            proc = subprocess.check_output(cmd.split(), cwd=CWD,
                    stderr=subprocess.PIPE, universal_newlines=True)
            revision = proc.strip()
        except Exception:
            # ok, don't bother
            revision = ''
    return revision


# have a way to test from python
def test():
    import pytest
    pytest.main([CWD,])
