# -*- coding: utf-8 -*-
import os

from setuptools import setup, find_packages

from grader import (
    __author__,
    __description__,
    __license__,
    __name__,
    __url__,
    __version__,
)

# this file is used to pick the relevant metadata for setup.py
INITFILE = os.path.join('grader', '__init__.py')
# the directory we are in
CWD = os.path.abspath(os.path.dirname(__file__))

# Get the long description from the README file
with open(os.path.join(CWD, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    version=__version__,
    author=__author__,
    description=__description__,
    long_description=long_description,
    license=__license__,
    name=__name__,
    url=__url__,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',  # noqa
        'Programming Language :: Python :: 3',
    ],
    keywords='grading applications',
    packages=find_packages(),
    install_requires=['pytest', 'numpy'],
    entry_points={
        'console_scripts': [
            'grader=grader.grader:main',
        ],
    },
)
