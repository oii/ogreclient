from __future__ import absolute_import
from __future__ import unicode_literals

import contextlib
import os
import platform
import subprocess

from collections import namedtuple

import mock
import pytest

from ..ogreclient.core import search_for_ebooks as func_search_for_ebooks
from ..ogreclient.ebook_obj import EbookObject
from ..ogreclient.prereqs import setup_ogreclient as func_setup_ogreclient
from ..ogreclient.prereqs import setup_user_auth as func_setup_user_auth
from ..ogreclient.prereqs import setup_ebook_home as func_setup_ebook_home
from ..ogreclient.printer import DummyPrinter


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
def client_config(calibre_ebook_meta_bin):
    return {
        'config_dir': None,
        'ebook_cache': mock.Mock(),
        'calibre_ebook_meta_bin': calibre_ebook_meta_bin,
        'providers': {},
        'ebook_home': None,
        'username': 'test',
        'password': 'test',
        'host': 'localhost:6543',
        'verbose': False,
        'quiet': True,
        'no_drm': True,
        'debug': True,
        'skip_cache': True,
    }


@pytest.fixture(scope='function')
def parse_author_method():
    return EbookObject._parse_author


@pytest.fixture(scope='function')
def helper_get_ebook(client_config, ebook_lib_path):
    def _get_ebook(filename, basepath=None):
        # ebook_obj creation helper
        ebook_obj = EbookObject(
            config=client_config,
            filepath=os.path.join(basepath, filename) if basepath else os.path.join(ebook_lib_path, filename),
        )
        ebook_obj.get_metadata()
        return ebook_obj

    return _get_ebook


@pytest.yield_fixture(scope='function')
def mock_urlopen():
    m = mock.patch('ogre.ogreclient.ogreclient.core.urllib2.urlopen')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_subprocess_popen(calibre_ebook_meta_bin):
    m = mock.patch('ogre.ogreclient.ogreclient.ebook_obj.subprocess.Popen')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_os_environ_get():
    m = mock.patch('ogre.ogreclient.ogreclient.prereqs.os.environ.get')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_subprocess_check_output():
    m = mock.patch('ogre.ogreclient.ogreclient.prereqs.subprocess.check_output')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_raw_input():
    m = mock.patch('__builtin__.raw_input')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_getpass_getpass():
    m = mock.patch('ogre.ogreclient.ogreclient.prereqs.getpass.getpass')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_os_mkdir():
    m = mock.patch('ogre.ogreclient.ogreclient.prereqs.os.mkdir')
    yield m.start()
    m.stop()


@pytest.fixture(scope='session')
def search_for_ebooks():
    def run_search_for_ebooks(client_config):
        data, _, errord = func_search_for_ebooks(client_config, prntr=DummyPrinter())
        return data, errord
    return run_search_for_ebooks


@pytest.fixture(scope='session')
def setup_ogreclient():
    def run_setup_ogreclient(mode, no_drm, host, ebook_home, username, password, ignore_kindle):
        # setup fake argparse object
        fakeargs = namedtuple(
            'fakeargs',
            ('mode', 'no_drm', 'host', 'ebook_home', 'username', 'password', 'ignore_kindle'),
        )
        return func_setup_ogreclient(
            fakeargs(mode, no_drm, host, ebook_home, username, password, ignore_kindle),
            prntr=DummyPrinter()
        )
    return run_setup_ogreclient


@pytest.fixture(scope='session')
def setup_user_auth():
    def run_setup_user_auth(client_config):
        # setup fake argparse object
        fakeargs = namedtuple('fakeargs', ('username', 'password'))
        return func_setup_user_auth(
            DummyPrinter(),
            fakeargs(None, None),
            client_config
        )
    return run_setup_user_auth


@pytest.fixture(scope='session')
def setup_ebook_home():
    def run_setup_ebook_home(client_config):
        # setup fake argparse object
        fakeargs = namedtuple('fakeargs', ('ebook_home'))
        _, ebook_home = func_setup_ebook_home(
            DummyPrinter(),
            fakeargs(None),
            client_config
        )
        return ebook_home
    return run_setup_ebook_home


@pytest.fixture(scope='session')
def cd():
    @contextlib.contextmanager
    def inner_cd(new_path):
        """ Context manager for changing the current working directory """
        saved_path = os.getcwd()
        try:
            os.chdir(new_path)
            yield new_path
        finally:
            os.chdir(saved_path)
    return inner_cd
