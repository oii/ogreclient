from __future__ import absolute_import
from __future__ import unicode_literals

import collections
import os
import platform
import subprocess
from urlparse import urlparse

import mock
import pytest

from ogreclient.core.ebook_obj import EbookObject
from ogreclient.utils.printer import CliPrinter


@pytest.fixture(scope='function')
def client_config(calibre_ebook_meta_bin):
    FakeUser = collections.namedtuple('FakeUser', ('username', 'password'))
    user = FakeUser('test', 'test')

    # no fancy printing during tests
    CliPrinter.init(quiet=True)

    # setup class vars on EbookObject
    EbookObject.calibre_ebook_meta_bin = calibre_ebook_meta_bin
    EbookObject.ebook_home = None

    FormatConfig = collections.namedtuple('FormatConfig', ('is_valid_format', 'is_non_fiction'))
    return {
        'config_dir': None,
        'ebook_cache': mock.Mock(),
        'calibre_ebook_meta_bin': calibre_ebook_meta_bin,
        'ebook_home': None,
        'providers': {},
        'username': user.username,
        'password': user.username,  # password=username during tests
        'host': urlparse('http://localhost:6543'),
        'definitions': collections.OrderedDict([
            ('mobi', FormatConfig(True, False)),
            ('pdf', FormatConfig(False, True)),
            ('azw3', FormatConfig(True, False)),
            ('epub', FormatConfig(True, False)),
        ]),
        'verbose': False,
        'no_drm': True,
        'debug': True,
        'skip_cache': True,
        'use_ssl': False,
    }


@pytest.fixture(scope='session')
def calibre_ebook_meta_bin():
    calibre_ebook_meta_bin = None

    if platform.system() == 'Darwin':
        # hardcoded path
        if not calibre_ebook_meta_bin and os.path.exists('/Applications/calibre.app/Contents/console.app/Contents/MacOS/ebook-meta'):
            calibre_ebook_meta_bin = '/Applications/calibre.app/Contents/console.app/Contents/MacOS/ebook-meta'

        # hardcoded path for pre-v2 calibre
        if not calibre_ebook_meta_bin and os.path.exists('/Applications/calibre.app/Contents/MacOS/ebook-meta'):
            calibre_ebook_meta_bin = '/Applications/calibre.app/Contents/MacOS/ebook-meta'
    else:
        try:
            # locate calibre's binaries with shell
            calibre_ebook_meta_bin = subprocess.check_output('which ebook-meta', shell=True).strip()
        except subprocess.CalledProcessError:
            pass

    return calibre_ebook_meta_bin


@pytest.fixture(scope='session')
def ebook_lib_path():
    # path where conftest.py resides + '/ebooks'
    return os.path.join(os.path.dirname(__file__), 'ebooks')


@pytest.fixture(scope='function')
def parse_author_method():
    return EbookObject._parse_author


@pytest.fixture(scope='function')
def helper_get_ebook(client_config, ebook_lib_path):
    def wrapped(filename, basepath=None):
        # ebook_obj creation helper
        ebook_obj = EbookObject(
            config=client_config,
            filepath=os.path.join(basepath, filename) if basepath else os.path.join(ebook_lib_path, filename),
            source='TEST'
        )
        ebook_obj.get_metadata()
        return ebook_obj

    return wrapped
