import pathlib

import pytest

from grader import grader2

TESTCSV = pathlib.Path('tests/data/year99/applications.csv')


def test_identity():
    id = 'alice'
    gr = grader2.Grader(id, TESTCSV)
    assert gr.identity == id
    gr.do_identity('bob')
    assert gr.identity == 'bob'

def test_no_identity():
    gr = grader2.Grader(None, TESTCSV)
    assert gr.identity is None

def test_unknown_identity():
    with pytest.raises(ValueError, match='charlie'):
        gr = grader2.Grader('charlie', TESTCSV)
