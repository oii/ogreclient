from __future__ import absolute_import
from __future__ import unicode_literals

import collections
import os
import platform
import subprocess
from urlparse import urlparse

import mock
import pytest

from ogreclient.core import scan_for_ebooks as func_scan_for_ebooks
from ogreclient.core import get_definitions as func_get_definitions
from ogreclient.ebook_obj import EbookObject
from ogreclient.prereqs import setup_user_auth as func_setup_user_auth
from ogreclient.prereqs import setup_ebook_home as func_setup_ebook_home
from ogreclient.printer import CliPrinter


@pytest.fixture(scope='function')
def client_config(calibre_ebook_meta_bin):
    FakeUser = collections.namedtuple('FakeUser', ('username', 'password'))
    user = FakeUser('test', 'test')

    # no fancy printing during tests
    CliPrinter.init(quiet=True)

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


@pytest.yield_fixture(scope='function')
def mock_connection():
    m = mock.patch('ogreclient.utils.OgreConnection')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_subprocess_popen(calibre_ebook_meta_bin):
    m = mock.patch('ogreclient.ebook_obj.subprocess.Popen')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_os_environ_get():
    m = mock.patch('ogreclient.prereqs.os.environ.get')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_subprocess_check_output():
    m = mock.patch('ogreclient.prereqs.subprocess.check_output')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_raw_input():
    m = mock.patch('__builtin__.raw_input')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_getpass_getpass():
    m = mock.patch('ogreclient.prereqs.getpass.getpass')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_os_mkdir():
    m = mock.patch('ogreclient.prereqs.os.mkdir')
    yield m.start()
    m.stop()


@pytest.fixture(scope='function')
def get_definitions():
    def wrapped(connection):
        return func_get_definitions(connection)
    return wrapped


@pytest.fixture(scope='session')
def search_for_ebooks():
    def wrapped(client_config):
        data, _, errord, _ = func_scan_for_ebooks(client_config)
        return data, errord
    return wrapped


@pytest.fixture(scope='session')
def setup_user_auth():
    def wrapped(client_config):
        # setup fake argparse object
        fakeargs = collections.namedtuple('fakeargs', ('host', 'username', 'password'))
        return func_setup_user_auth(
            fakeargs(None, None, None),
            client_config
        )
    return wrapped


@pytest.fixture(scope='session')
def setup_ebook_home():
    def wrapped(client_config):
        # setup fake argparse object
        fakeargs = collections.namedtuple('fakeargs', ('ebook_home'))
        _, ebook_home = func_setup_ebook_home(
            fakeargs(None),
            client_config
        )
        return ebook_home
    return wrapped
