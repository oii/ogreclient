from __future__ import absolute_import
from __future__ import unicode_literals

import copy
import mock
import os
import pytest
import yaml

import whoosh

from ogreserver.models.amazon import AmazonAPI
from ogreserver.models.goodreads import GoodreadsAPI
from ogreserver.models.search import Search

import fixtures


@pytest.yield_fixture(scope='function')
def search(flask_app):
    search = Search(flask_app.whoosh, pagelen=100)
    yield search
    with flask_app.whoosh.writer() as writer:
        writer.mergetype = whoosh.writing.CLEAR


@pytest.fixture(scope='function')
def amazon(app_config, logger):
    return AmazonAPI(
        logger,
        app_config.get('AWS_ADVERTISING_API_ACCESS_KEY', None),
        app_config.get('AWS_ADVERTISING_API_SECRET_KEY', None),
        app_config.get('AWS_ADVERTISING_API_ASSOCIATE_TAG', None),
    )

@pytest.yield_fixture(scope='function')
def mock_amazon():
    m = mock.patch('ogreserver.models.amazon.bottlenose.Amazon')
    yield m.start()
    m.stop()


@pytest.fixture(scope='session')
def goodreads(app_config, logger):
    return GoodreadsAPI(logger, app_config.get('GOODREADS_API_KEY', None))

@pytest.yield_fixture(scope='function')
def mock_goodreads():
    m = mock.patch('ogreserver.models.goodreads.requests')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_subprocess_popen(request):
    m = mock.patch('ogreserver.models.conversion.subprocess.Popen')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_subprocess_check_call(request):
    m = mock.patch('ogreserver.models.conversion.subprocess.check_call')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_subprocess_check_output(request):
    m = mock.patch('ogreserver.models.conversion.subprocess.check_output')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_connect_s3(request):
    m = mock.patch('ogreserver.models.conversion.connect_s3')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_compute_md5(request):
    m = mock.patch('ogreserver.models.conversion.compute_md5')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_shutil_move(request):
    m = mock.patch('ogreserver.models.conversion.shutil.move')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_shutil_copy(request):
    m = mock.patch('ogreserver.models.conversion.shutil.copy')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_utils_make_tempdir(request):
    m = mock.patch('ogreserver.models.conversion.make_temp_directory')
    yield m.start()
    m.stop()


@pytest.yield_fixture(scope='function')
def mock_views_api_open(request):
    m = mock.patch('ogreserver.views.api.open', mock.mock_open(read_data='API open() data'))
    yield m.start()
    m.stop()


@pytest.fixture(scope='session')
def get_data_fixtures():
    """
    Load a set data fixtures for a particular test. Fixtures must be stored in:
        <test_filename>_fixtures/<testname>.yaml

    This YAML file should contain all fixtures for the test.
    """
    def wrapped(file_path, test_name):
        fixture_path = os.path.join(
            '{}_fixtures'.format(file_path[:-3]),
            '{}.yaml'.format(test_name.split('.')[-1:][0])
        )
        with open(fixture_path, 'r') as f:
            return yaml.load(f.read())
    return wrapped


@pytest.fixture(scope='function')
def ebook_fixture_azw3():
    return copy.deepcopy(fixtures.EBOOK_FIXTURE_1)


@pytest.fixture(scope='function')
def ebook_fixture_pdf():
    return copy.deepcopy(fixtures.EBOOK_FIXTURE_2)


@pytest.fixture(scope='function')
def ebook_fixture_epub():
    return copy.deepcopy(fixtures.EBOOK_FIXTURE_3)


@pytest.fixture(scope='function')
def ebook_sync_fixture_1(ebook_fixture_azw3):
    return {
        "H. C.\u0006Andersen\u0007Andersen's Fairy Tales": ebook_fixture_azw3
    }


@pytest.fixture(scope='function')
def ebook_sync_fixture_2(ebook_fixture_pdf):
    return {
        'Eggbert\u0006Yolker\u0007The Sun is an Egg': ebook_fixture_pdf
    }
