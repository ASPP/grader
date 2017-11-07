"""Grader: a Python module and command-line utility to grade applications.
"""

# Always prefer setuptools over distutils
from setuptools import setup, find_packages
# To use a consistent encoding
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='grader',
    version='0.1.0',
    description='A Python module and command-line utility to grade applications.',
    long_description=long_description,
    url='https://github.com/ASPP/grader',
    author='grader contributors',
    license='GPLv3+',
    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Programming Language :: Python :: 3',
    ],
    keywords='grading applications',
    packages=find_packages(),
    install_requires=['pytest'],
    package_data={
        #'sample': ['package_data.dat'],
    },
    entry_points={
        'console_scripts': [
            'grader=grader.grader:main',
        ],
    },
)
