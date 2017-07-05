from __future__ import absolute_import
from __future__ import unicode_literals

import codecs
import getpass
import os
import platform
import subprocess
import sys
from urlparse import urlparse

from .cache import Cache
from .config import write_config
from .core import get_definitions
from .dedrm import download_dedrm
from .definitions import OGRE_PROD_HOST
from .exceptions import (ConfigSetupError, NoEbookSourcesFoundError, DeDrmNotAvailable,
                         EbookHomeMissingError, CalibreNotAvailable)
from .printer import CliPrinter
from .providers import PROVIDERS, find_ebook_providers
from .utils import OgreConnection


prntr = CliPrinter.get_printer()


def setup_ogreclient(args, conf):
    check_calibre_exists(conf)

    # not all commands need ogreserver
    if hasattr(args, 'host'):
        setup_ogreserver_connection_and_get_definitions(args, conf)

    # all commands execpt dedrm need providers
    if args.mode in ('init', 'sync', 'stats', 'scan'):
        setup_providers(args, conf)

    # write out this config for next run
    write_config(conf)

    # setup the sqlite cache
    init_cache(conf)

    # ensure the DRM tools are installed and up-to-date
    if args.mode == 'sync':
        if args.no_drm is True:
            # skip drm check
            pass
        else:
            dedrm_check(args, conf)

    elif args.mode == 'init':
        dedrm_check(args, conf)

    if args.mode == 'stats' and 'username' not in conf:
        # supply a default username during stats queries
        conf['username'] = 'oc'

    # return config object
    return conf


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
                raise CalibreNotAvailable('Calibre could not be found in OGRE program directory!')

        elif platform.system() == 'Linux':
            try:
                # locate calibre's binaries with shell
                calibre_ebook_meta_bin = subprocess.check_output('which ebook-meta', shell=True).strip()
            except subprocess.CalledProcessError:
                pass

        # ogreclient requires calibre (unfortunately)
        if not calibre_ebook_meta_bin:
            raise CalibreNotAvailable('You must install Calibre in order to use ogreclient.')

        # init the config dict
        conf['calibre_ebook_meta_bin'] = calibre_ebook_meta_bin


def setup_ogreserver_connection_and_get_definitions(args, conf):
    '''
    Load user's credentials & the ogreserver hostname from the CLI/environment
    Create a Connection object and login
    Load the definitions from ogreserver
    '''
    # setup user auth creds
    conf['host'], conf['username'], conf['password'] = setup_user_auth(args, conf)

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
    if args.host:
        conf['ignore_ssl_errors'] = True

    # authenticate user and generate session API key
    connection = OgreConnection(conf, debug=args.debug)
    connection.login(conf['username'], conf['password'])

    # query the server for current ebook definitions (which file extensions to scan for etc)
    conf['definitions'] = get_definitions(connection)

    return connection


def setup_providers(args, conf):
    '''
    Validate OGRE_HOME and ebooks providers (kindle etc) on the local machine
    '''
    ebook_home_found, conf['ebook_home'] = setup_ebook_home(args, conf)

    if not os.path.exists(conf['ebook_home']):
        raise EbookHomeMissingError("Path specified in OGRE_HOME doesn't exist!")

    conf['ignore_providers'] = []

    # ignore certain providers as determined by --ignore-* params
    for provider in PROVIDERS.keys():
        ignore_str = 'ignore_{}'.format(provider)
        if ignore_str in vars(args) and vars(args)[ignore_str] is True:
            conf['ignore_providers'].append(provider)

    # scan for ebook-provider directories; modifies config in-place
    find_ebook_providers(conf, ignore=conf['ignore_providers'])

    # hard error if no ebook provider dirs found
    if ebook_home_found is False and not conf['providers']:
        raise NoEbookSourcesFoundError


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


def dedrm_check(args, conf):
    '''
    Check for and attempt to install dedrm tools
    '''
    # check if we have decrypt capability
    from .dedrm import CAN_DECRYPT

    if platform.system() == 'Linux':
        prntr.info('DeDRM in not supported under Linux')
        return

    if CAN_DECRYPT is False:
        if not hasattr(args, 'host'):
            raise DeDrmNotAvailable((
                'DeDRM tools are not yet installed. '
                'Please re-run with --host, --username & --password parameters to install them.'
            ))

        # attempt to download and setup dedrm
        attempted_download = True
        installed = download_dedrm(conf, debug=args.debug)

        if installed is None:
            # auth failed contacting ogreserver
            return
    else:
        attempted_download = False
        installed = False

    from .dedrm import init_keys

    # initialise a working dedrm lib
    if CAN_DECRYPT is True or installed is True:
        msgs = init_keys(conf['config_dir'], ignore_check=True)
        for m in msgs:
            prntr.info(m)

        from dedrm import PLUGIN_VERSION
        prntr.info('Initialised DeDRM tools v{}'.format(PLUGIN_VERSION))

    elif attempted_download is True:
        prntr.error('Failed to download DRM tools. Please report this error.')


def setup_user_auth(args, conf):
    """
    Setup user auth credentials, sourced in this order:
     - CLI params
     - ENV vars
     - Saved values in ogre config
     - CLI readline interface
    """
    # 1) load CLI parameters
    host = args.host
    username = args.username
    password = args.password

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
            raise ConfigSetupError('O.G.R.E. username not supplied')

    # 4.3) load password via readline
    if not password:
        prntr.info('Please enter your password, or press enter to exit:')
        password = getpass.getpass()
        if len(password) == 0:
            raise ConfigSetupError('O.G.R.E. password not supplied')

    return host, username, password


def setup_ebook_home(args, conf):
    """
    Setup user's ebook home, config being set with this order of precedence:
     - CLI params
     - ENV vars
     - saved values in ogre config
     - automatically created in $HOME
    """
    ebook_home = None

    # 1) load CLI parameters (if available)
    try:
        ebook_home = args.ebook_home
    except AttributeError:
        pass

    # 2) load ENV vars
    if ebook_home is None:
        ebook_home = os.environ.get('OGRE_HOME')

    # 3) load settings from saved config
    if ebook_home is None or len(ebook_home) == 0:
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
