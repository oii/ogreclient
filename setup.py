#! /usr/bin/env python

import os
import sys

import ogreclient

from setuptools import setup, find_packages

if sys.argv[-1] == 'publish':
    os.system('python setup.py sdist upload')
    sys.exit()

requires = [
    'requests'
]

if sys.version_info < (2, 7):
    requires += ['argparse']

setup(
    name='ogreclient',
    version=ogreclient.__version__,
    description='Client for private OGRE system',
    long_description='Client for private OGRE system',
    author='Matt Black',
    author_email='dev@mafro.net',
    url='http://github.com/oii/ogre',
    packages=find_packages(exclude=['tests']),
    package_data={'': ['LICENSE']},
    install_requires=requires,
    entry_points = {
        'console_scripts': [
            'ogre=ogreclient.cli:entrypoint'
        ]
    },
    license=open('LICENSE').read(),
    classifiers=(
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Religion',
        'Natural Language :: English',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
    ),
)
