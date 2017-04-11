from __future__ import absolute_import
from __future__ import unicode_literals

import collections
import datetime
import json
import logging
import os
import platform
import random
import shutil
import string
import subprocess
import threading
from urlparse import urlparse

import boto.exception
import mock
import pytest
import virtualenvapi.manage

from ogreserver.utils import connect_s3
from ogreclient.ogreclient.printer import CliPrinter


def pytest_addoption(parser):
    parser.addoption('--only-client',
        action='store_true',
        help='Skip all the server fixtures whose libs are missing for ogreclient'
    )


@pytest.fixture(scope='session')
def app_config():
    FormatConfig = collections.namedtuple('FormatConfig', ('is_valid_format', 'is_non_fiction'))
    return {
        'DEBUG': True,
        'BETA': False,
        'TESTING': True,
        'TESTING_LOG_PATH': 'ogreserver.log',

        'SECRET_KEY': 'its_a_secret',

        'AWS_ADVERTISING_API_ACCESS_KEY': 'its_a_secret',
        'AWS_ADVERTISING_API_SECRET_KEY': 'its_a_secret',
        'AWS_ADVERTISING_API_ASSOCIATE_TAG': 'its_a_secret',

        'GOODREADS_API_KEY': 'its_a_secret',

        'BROKER_URL': 'amqp://dev:dev@localhost:5672/dev',
        'CELERY_DEFAULT_QUEUE': 'testing',
        'CELERY_DEFAULT_EXCHANGE_TYPE': 'direct',
        'CELERY_DEFAULT_ROUTING_KEY': 'testing',
        'CELERY_DEFAULT_EXCHANGE': 'testing',

        'CELERY_ALWAYS_EAGER': True,

        'AWS_ACCESS_KEY': '',
        'AWS_SECRET_KEY': '',
        'AWS_REGION': '',
        'EBOOK_S3_BUCKET': 'ogre-testing',
        'DIST_S3_BUCKET': 'ogre-testing',
        'DEDRM_VERSION': '0.0.1',

        'EBOOK_DEFINITIONS': collections.OrderedDict([
            ('mobi', FormatConfig(True, False)),
            ('pdf', FormatConfig(False, True)),
            ('azw3', FormatConfig(True, False)),
            ('epub', FormatConfig(True, False)),
        ]),

        'EBOOK_FORMATS': ['egg', 'mobi', 'azw3'],
        'DOWNLOAD_LINK_EXPIRY': 10,

        'DB_HOST': 'localhost',
        'DB_USER': 'ogre',
        'DB_PASS': 'oii',
        'DB_NAME': 'test',

        'WHOOSH_BASE': 'test.db',
        'UPLOADED_EBOOKS_DEST': 'uploads',
        'UPLOADED_LOGS_DEST': 'logs',

        'RETHINKDB_DATABASE': 'test',

        'SECURITY_PASSWORD_HASH': str('pbkdf2_sha256'),
        'SECURITY_PASSWORD_SALT': 'test',
        'SECURITY_TOKEN_AUTHENTICATION_HEADER': 'Ogre-Key',
        'SECURITY_USER_IDENTITY_ATTRIBUTES': ['email', 'username'],
    }


@pytest.yield_fixture(scope='session')
def _flask_app(request, app_config):
    if request.config.getoption('--only-client'):
        yield None
        return

    from ogreserver.factory import create_app, make_celery, configure_extensions, \
            register_blueprints, register_signals
    from ogreserver.extensions.celery import register_tasks

    app = create_app(app_config)
    app.testing = True
    app.celery = make_celery(app)
    register_tasks(app)
    configure_extensions(app)
    register_blueprints(app)
    register_signals(app)
    yield app
    if os.path.exists(app_config['WHOOSH_BASE']):
        shutil.rmtree(app_config['WHOOSH_BASE'])


@pytest.yield_fixture(scope='function')
def flask_app(request, _flask_app):
    # mock all signals attached to the Flask app
    for name in _flask_app.signals.keys():
        _flask_app.signals[name] = mock.Mock()
    yield _flask_app


@pytest.fixture(scope='session')
def ogreserver(request, _flask_app):
    if request.config.getoption('--only-client'):
        return

    from wsgiref.simple_server import make_server

    server = make_server('', 6543, _flask_app)
    app_thread = threading.Thread(target=server.serve_forever)
    app_thread.start()
    def fin():
        threading.Thread(target=server.shutdown).start()
    request.addfinalizer(fin)
    return app_thread


def terminate_db_connections(engine, db_name):
    # terminate any existing DB connections
    text = '''
    SELECT pg_terminate_backend(pg_stat_activity.pid)
    FROM pg_stat_activity
    WHERE pg_stat_activity.datname = '{}'
      AND pid <> pg_backend_pid();
    '''.format(db_name)
    engine.execute(text)


@pytest.yield_fixture(scope='session')
def postgresql(request, _flask_app):
    if request.config.getoption('--only-client'):
        yield None
        return

    import sqlalchemy
    from ogreserver.extensions.database import setup_db_session, create_tables

    # update DB connection string
    _flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}/test'.format(**_flask_app.config)

    # use raw sqlalchemy for create/drop DB
    engine = sqlalchemy.create_engine(
        'postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}/'.format(**_flask_app.config)
    )

    def run_query(sql):
        # get the internal connection obj, close the open transaction, then run
        conn = engine.connect()
        conn.execute('commit')
        conn.execute(sql)
        conn.close()

    # create a test database using sqlalchemy
    run_query('drop database if exists test')
    run_query('create database test')

    with _flask_app.test_request_context():
        # init app tables into test database
        db_session = setup_db_session(_flask_app)
        create_tables(_flask_app)
        yield db_session

    # terminate any existing DB connections
    terminate_db_connections(engine, 'test')

    # cleanup the test mysql db
    run_query('drop database if exists test')


@pytest.fixture(scope='session')
def user(request, postgresql):
    if request.config.getoption('--only-client'):
        return

    return _create_user(request, postgresql)

@pytest.fixture(scope='session')
def user2(request, postgresql):
    if request.config.getoption('--only-client'):
        return

    return _create_user(request, postgresql)

def _create_user(request, postgresql):
    from ogreserver.models.user import User

    # create random username
    username = ''.join(random.choice(string.ascii_lowercase) for n in range(6))
    # create user in auth DB
    user = User(username, password=username, email='{}@example.com'.format(username), active=True, roles=[])
    user.confirmed_at = datetime.datetime.utcnow()
    user.preferred_ebook_format = 'mobi'
    postgresql.add(user)
    postgresql.commit()
    return user


@pytest.fixture(scope='session')
def ogreclient_auth_token(_flask_app, user):
    client = _flask_app.test_client()
    result = client.post(
        '/login',
        data=json.dumps({'email': user.email, 'password': user.username}),
        content_type='application/json'
    )
    return json.loads(result.data)['response']['user']['authentication_token']


@pytest.yield_fixture(scope='session')
def _rethinkdb(request):
    if request.config.getoption('--only-client'):
        yield None
        return

    import rethinkdb as r
    conn = r.connect('localhost', 28015)

    # drop/create test database
    if 'test' in r.db_list().run(conn):
        r.db_drop('test').run(conn)
    r.db_create('test').run(conn)

    # reconnect with db=test and repl
    r.connect(db='test').repl()

    r.table_create('ebooks', primary_key='ebook_id').run()
    r.table_create('versions', primary_key='version_id').run()
    r.table_create('formats', primary_key='file_hash').run()
    r.table_create('sync_events').run()

    def create_index(table, name, index=None):
        if name not in r.table(table).index_list().run():
            if index is None:
                r.db('test').table(table).index_create(name).run()
            else:
                r.db('test').table(table).index_create(name, index).run()
            r.db('test').table(table).index_wait(name).run()

    # create FK indexes
    create_index(
        'ebooks', 'authortitle',
        index=[r.row['author'].downcase(), r.row['title'].downcase()]
    )
    create_index('ebooks', 'asin', index=r.row['meta']['asin'])
    create_index('ebooks', 'isbn', index=r.row['meta']['isbn'])
    create_index('versions', 'ebook_id')
    create_index('versions', 'original_filehash')
    create_index('versions', 'ebook_username', index=[r.row['ebook_id'], r.row['username']])
    create_index('formats', 'version_id')
    create_index('formats', 'uploaded')
    create_index('formats', 'uploaded_by')
    create_index('formats', 'uploadedby_dedrm', index=[r.row['uploaded_by'], r.row['dedrm']])
    create_index('sync_events', 'username')
    create_index('sync_events', 'timestamp')
    create_index('sync_events', 'user_new_books_count', index=[r.row['username'], r.row['new_books_count']])

    yield r

    # remove test database
    if 'test' in r.db_list().run(conn):
        r.db_drop('test').run(conn)
    conn.close()


@pytest.fixture(scope='function')
def rethinkdb(request, _rethinkdb):
    _rethinkdb.db('test').table('ebooks').delete().run()
    _rethinkdb.db('test').table('versions').delete().run()
    _rethinkdb.db('test').table('formats').delete().run()
    return _rethinkdb


@pytest.fixture(scope='function')
def datastore(request, flask_app):
    from ogreserver.models.datastore import DataStore
    return DataStore(flask_app.config, flask_app.logger)


@pytest.fixture(scope='function')
def conversion(request, app_config, datastore, flask_app):
    from ogreserver.models.conversion import Conversion
    return Conversion(app_config, datastore)


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


@pytest.fixture(scope='function')
def client_config(flask_app, calibre_ebook_meta_bin, user):
    # when fixture used with --only-client, must fake a User model
    if user is None:
        class FakeUser():
            username = 'test'
            password = 'test'
        user = FakeUser()

    # no fancy printing during tests
    CliPrinter.init(quiet=True)

    return {
        'config_dir': None,
        'ebook_cache': mock.Mock(),
        'calibre_ebook_meta_bin': calibre_ebook_meta_bin,
        'ebook_home': None,
        'providers': {},
        'username': user.username,
        'password': user.username,  # password=username during tests
        'host': urlparse('http://localhost:6543'),
        'definitions': flask_app.config['EBOOK_DEFINITIONS'],
        'verbose': False,
        'no_drm': True,
        'debug': True,
        'skip_cache': True,
        'use_ssl': False,
    }


@pytest.fixture(scope='session')
def ebook_lib_path():
    # path where conftest.py resides + '/ebooks'
    return os.path.join(os.path.dirname(__file__), 'tests', 'ebooks')


@pytest.fixture(scope='function')
def virtualenv(tmpdir):
    # create a virtualenv in a tmpdir; pytest will clean up for us
    return virtualenvapi.manage.VirtualEnvironment(
        os.path.join(tmpdir.strpath, 'ogreclient')
    )


@pytest.fixture
def client_sync(request):
    '''
    Wrap the ogreclient sync() function with another which provides a CliPrinter
    and captures all the output from the sync
    '''
    if request.config.getoption('--only-client'):
        return

    from ogreclient.ogreclient.core import sync
    from ogreclient.ogreclient.printer import CliPrinter

    # set printer to capture all logs
    prntr = CliPrinter.get_printer()
    CliPrinter.init(log_output=True)

    def wrapped(config):
        sync(config)
        return prntr.logs
    return wrapped


@pytest.fixture(scope='session')
def logger():
    logger = logging.getLogger('testing')
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.DEBUG)
    return logger


@pytest.yield_fixture(scope='function')
def s3bucket(app_config):
    s3 = connect_s3(app_config)
    try:
        bucket = s3.create_bucket(app_config['EBOOK_S3_BUCKET'])
    except boto.exception.S3CreateError:
        bucket = s3.get_bucket(app_config['EBOOK_S3_BUCKET'])
    yield bucket
    for k in bucket.list():
        k.delete()
    s3.delete_bucket(bucket)
