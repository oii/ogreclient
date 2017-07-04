from __future__ import absolute_import
from __future__ import unicode_literals

import codecs
import getpass
import os
import platform
import subprocess
import sys
from urlparse import urlparse

from dedrm import PLUGIN_VERSION as DEDRM_PLUGIN_VERSION

from ogreclient import exceptions, OGRE_PROD_HOST
from ogreclient.core.ebook_obj import EbookObject
from ogreclient.config import deserialize_defs, read_config, write_config
from ogreclient.providers import find_ebook_providers
from ogreclient.utils.cache import Cache
from ogreclient.utils.connection import OgreConnection
from ogreclient.utils.dedrm import init_keys
from ogreclient.utils.printer import CliPrinter


prntr = CliPrinter.get_printer()


def setup_ogreclient(host=None, username=None, password=None, ebook_home=None):
    # read previous config
    conf = read_config()

    check_calibre_exists(conf)

    # find ebook providers
    setup_providers(conf, ebook_home)

    # setup connection to ogreserver
    setup_connection_and_get_definitions(
        conf,
        host=host,
        username=username,
        password=password,
    )

    # write out this config for next run
    write_config(conf)

    # setup the sqlite cache
    init_cache(conf)

    # check dedrm is working
    dedrm_check(conf)

    #if args.mode == 'stats' and 'username' not in conf:
    #    # supply a default username during stats queries
    #    conf['username'] = 'oc'

    # return config object
    return conf


def get_definitions(connection):
    try:
        # retrieve the ebook format definitions
        data = connection.request('definitions')

        # convert list of lists result into OrderedDict
        return deserialize_defs(data)

    except exceptions.RequestError as e:
        raise exceptions.FailedGettingDefinitionsError(inner_excp=e)


def check_calibre_exists(conf):
    '''
    Validate the local machine has calibre available, and set calibre_ebook_meta_bin in conf
    '''
    if 'calibre_ebook_meta_bin' not in conf:
        calibre_ebook_meta_bin = None

        if platform.system() == 'Darwin':
            # hardcoded path
            if os.path.exists('/Applications/calibre.app/Contents/console.app/Contents/MacOS/ebook-meta'):
                calibre_ebook_meta_bin = '/Applications/calibre.app/Contents/console.app/Contents/MacOS/ebook-meta'

            # hardcoded path for pre-v2 calibre
            elif os.path.exists('/Applications/calibre.app/Contents/MacOS/ebook-meta'):
                calibre_ebook_meta_bin = '/Applications/calibre.app/Contents/MacOS/ebook-meta'

        elif platform.system() == 'Windows':
            # calibre is packaged with ogreclient on Windows
            ogre_win_path = os.path.dirname(__file__)[0:os.path.dirname(__file__).index('OGRE')+4]

            calibre_ebook_meta_bin = os.path.join(ogre_win_path, 'CalibrePortable\Calibre\ebook-meta.exe')

            if not os.path.exists(calibre_ebook_meta_bin):
                raise exceptions.CalibreNotAvailable('Calibre could not be found in OGRE program directory!')

        elif platform.system() == 'Linux':
            try:
                # locate calibre's binaries with shell
                calibre_ebook_meta_bin = subprocess.check_output('which ebook-meta', shell=True).strip()
            except subprocess.CalledProcessError:
                pass

        # ogreclient requires calibre (unfortunately)
        if not calibre_ebook_meta_bin:
            raise exceptions.CalibreNotAvailable('You must install Calibre in order to use ogreclient.')

        # store in config for next run
        conf['calibre_ebook_meta_bin'] = calibre_ebook_meta_bin

    # make accessible as class variable on EbookObject
    EbookObject.calibre_ebook_meta_bin = conf['calibre_ebook_meta_bin']


def setup_connection_and_get_definitions(conf, host=None, username=None, password=None, debug=False):
    '''
    Load user's credentials & the ogreserver hostname from the CLI/environment
    Create a Connection object and login
    Load the definitions from ogreserver
    '''
    # setup connection details
    conf['host'], conf['username'], conf['password'] = setup_user_auth(
        conf,
        host=host,
        username=username,
        password=password,
    )

    # include http:// on host if missing
    if not conf['host'].startswith('http'):
        conf['host'] = 'http://{}'.format(conf['host'])

    # parse protocol/hostname/port
    conf['host'] = urlparse(conf['host'])

    # always use SSL in production
    if conf['host'].scheme == 'https' or conf['host'].netloc == OGRE_PROD_HOST:
        conf['use_ssl'] = True
        conf['ignore_ssl_errors'] = False

    # TODO beta only
    conf['ignore_ssl_errors'] = True

    # if --host supplied CLI, ignore SSL errors on connect
    if conf['host']:
        conf['ignore_ssl_errors'] = True

    # authenticate user and generate session API key
    connection = OgreConnection(conf, debug=debug)
    connection.login(conf['username'], conf['password'])

    # query the server for current ebook definitions (which file extensions to scan for etc)
    conf['definitions'] = get_definitions(connection)

    return connection


def setup_providers(conf, ebook_home):
    '''
    Validate OGRE_HOME and ebooks providers (kindle etc) on the local machine
    '''
    ebook_home_found, conf['ebook_home'] = setup_ebook_home(conf, ebook_home)

    # make accessible as class variable on EbookObject
    EbookObject.ebook_home = conf['ebook_home']

    if not os.path.exists(conf['ebook_home']):
        raise exceptions.EbookHomeMissingError("Path specified in OGRE_HOME doesn't exist!")

    conf['ignore_providers'] = []

    ## ignore certain providers as determined by --ignore-* params
    #for provider in PROVIDERS.keys():
    #    ignore_str = 'ignore_{}'.format(provider)
    #    if ignore_str in vars(args) and vars(args)[ignore_str] is True:
    #        conf['ignore_providers'].append(provider)

    # scan for ebook-provider directories; modifies config in-place
    find_ebook_providers(conf, ignore=conf['ignore_providers'])

    # hard error if no ebook provider dirs found
    if ebook_home_found is False and not conf['providers']:
        raise exceptions.NoEbookSourcesFoundError


def init_cache(conf):
    '''
    Setup the Cache object for tracking ebooks in sqlite
    '''
    # setup some ebook cache file paths
    conf['ebook_cache'] = Cache(conf, os.path.join(conf['config_dir'], 'ebook_cache.db'))

    # verify the ogreclient cache; true means it was initialised
    if conf['ebook_cache'].verify_cache():
        prntr.info('Please note that metadata/DRM scanning means the first run of ogreclient '
                'will be much slower than subsequent runs.')


def dedrm_check(conf):
    '''
    Check for and attempt to install dedrm tools
    '''
    if platform.system() == 'Linux':
        prntr.info('DeDRM in not supported under Linux')
        return

    # initialise a working dedrm lib
    msgs = init_keys(conf['config_dir'])
    for m in msgs:
        prntr.info(m)

    prntr.info('Initialised DeDRM tools v{}'.format(DEDRM_PLUGIN_VERSION))


def setup_user_auth(conf, host, username, password):
    """
    Setup user auth credentials, sourced in this order:
     - CLI params
     - ENV vars
     - Saved values in ogre config
     - CLI readline interface
    """
    # 2) load ENV vars
    if host is None:
        host = os.environ.get('OGRE_HOST')
    if username is None:
        username = os.environ.get('OGRE_USER')
    if password is None:
        password = os.environ.get('OGRE_PASS')

    # 3) load settings from saved config
    if not host:
        host = conf.get('host')
    if not username:
        username = conf.get('username')
    if not password:
        password = conf.get('password')

    # 4.1) default to prod hostname
    if not host:
        host = OGRE_PROD_HOST

    # 4.2) load username via readline
    if not username:
        prntr.info("Please enter your O.G.R.E. username, or press enter to use '{}':".format(getpass.getuser()))
        ri = raw_input()
        if len(ri) > 0:
            username = ri
        else:
            username = getpass.getuser()

        # final username verification
        if not username:
            raise exceptions.OgreException('O.G.R.E. username not supplied')

    # 4.3) load password via readline
    if not password:
        prntr.info('Please enter your password, or press enter to exit:')
        password = getpass.getpass()
        if len(password) == 0:
            raise exceptions.OgreException('O.G.R.E. password not supplied')

    return host, username, password


def setup_ebook_home(conf, ebook_home):
    """
    Setup user's ebook home, config being set with this order of precedence:
     - CLI param
     - ENV var
     - saved values in ogre config
     - automatically created in $HOME
    """
    # 2) load ENV vars
    if not ebook_home:
        ebook_home = os.environ.get('OGRE_HOME')

    # 3) load settings from saved config
    if not ebook_home:
        ebook_home = conf.get('ebook_home', None)

    if type(ebook_home) is str:
        # decode ebook_home to unicode according to local fs encoding,
        # os.walk/os.listdir then does all further charset conversion for us
        ebook_home = codecs.decode(ebook_home, sys.getfilesystemencoding())

    # handle no ebook home :(
    if ebook_home is None:
        ebook_home_found = False

        # get the user's HOME directory
        home_dir = os.path.expanduser('~')

        # setup ebook home cross-platform
        if platform.system() == 'Darwin':
            ebook_home = os.path.join(home_dir, 'Documents/ogre-ebooks')
        else:
            ebook_home = os.path.join(home_dir, 'ogre-ebooks')

        # create OGRE ebook_home for the user :)
        if not os.path.exists(ebook_home):
            if not os.path.exists(os.path.join(home_dir, 'Documents')):
                os.mkdir(os.path.join(home_dir, 'Documents'))
            os.mkdir(ebook_home)
            prntr.info('Decrypted ebooks will be put into {}'.format(ebook_home))
    else:
        ebook_home_found = True

    return ebook_home_found, ebook_home
