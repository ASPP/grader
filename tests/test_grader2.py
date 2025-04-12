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

def test_archive():
    gr = grader2.Grader(None, TESTCSV)
    # we have year 2009 and year 2019
    assert len(gr.archive) == 2
    for apps in gr.archive:
        assert len(apps.people) == 2

def test_setting_n_applied():
    gr = grader2.Grader(None, TESTCSV)
    # Bob Travolta applied twice in our dataset
    bobs = gr.applications.filter(name='Bob')
    assert len(bobs) == 1
    bob = bobs[0]
    # n_applied is the number of times applied before
    assert bob.n_applied == 1
