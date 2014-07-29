from __future__ import absolute_import

import getpass
import json
import os
import platform
import subprocess
import sys

from .cache import Cache
from .dedrm import download_dedrm
from .exceptions import ConfigSetupError


def setup_ogreclient(args, prntr):
    first_scan_warning = False

    # setup some ebook cache file paths
    config_dir = os.path.join(os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config')), 'ogre')
    ebook_cache = Cache(os.path.join(config_dir, 'ebook_cache.db'))

    # use existing config if available
    if os.path.exists(config_dir) and os.path.exists(os.path.join(config_dir, 'app.config')):
        with open(os.path.join(config_dir, 'app.config'), 'r') as f_config:
            conf = json.loads(f_config.read())

    # create a config directory in $HOME on first run
    elif not os.path.exists(config_dir) or not os.path.exists(os.path.join(config_dir, 'app.config')):
        first_scan_warning = True

        if not os.path.exists(config_dir):
            os.makedirs(config_dir)

        calibre_ebook_meta_bin = ''

        try:
            # locate calibre's binaries with shell
            calibre_ebook_meta_bin = subprocess.check_output('which ebook-meta', shell=True).strip()
        except subprocess.CalledProcessError:
            # filesystem search
            if os.path.exists('/Applications/Calibre.app'):
                try:
                    calibre_ebook_meta_bin = subprocess.check_output(
                        'find /Applications/Calibre.app -type f -name ebook-meta', shell=True
                    ).strip()
                except subprocess.CalledProcessError:
                    pass

        # ogreclient requires calibre (unfortunately)
        if len(calibre_ebook_meta_bin) == 0:
            prntr.e('You must install Calibre in order to use ogreclient.')
            prntr.e('Please follow the simple instructions at http://ogre.oii.yt/install')
            sys.exit(1)

        # init the config dict
        conf = {
            'calibre_ebook_meta_bin': calibre_ebook_meta_bin
        }

    # setup user auth perms, with this order of precedence:
    #  - CLI params
    #  - ENV vars
    #  - saved values in ogre config
    #  - CLI readline interface
    # output is written directly into conf var
    setup_user_auth(prntr, args, conf)

    # write the config file
    with open(os.path.join(config_dir, 'app.config'), 'w') as f_config:
        f_config.write(json.dumps(conf))

    # return the config directory
    conf['config_dir'] = config_dir

    # return the user's OS
    conf['platform'] = platform.system()

    # verify the ogreclient cache; true means it was initialised
    if ebook_cache.verify_cache(prntr):
        first_scan_warning = True

    if args.mode == 'sync' and args.no_drm is True:
        # skip drm check
        pass
    else:
        dedrm_check(prntr, args, conf)

    if first_scan_warning is True:
        prntr.p('Please note that DRM scanning means the first run of ogreclient '
                'will be much slower than subsequent runs.')

    # return config object
    conf['ebook_cache'] = ebook_cache
    return conf


def dedrm_check(prntr, args, conf):
    # check if we have decrypt capability
    from .dedrm import CAN_DECRYPT

    if CAN_DECRYPT is False:
        # attempt to download and setup dedrm
        attempted_download = True
        installed = download_dedrm(
            args.host, conf['username'], conf['password'], prntr, debug=args.debug
        )

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
            prntr.p(m)

        from dedrm import PLUGIN_VERSION
        prntr.p('Initialised DeDRM tools v{}'.format(PLUGIN_VERSION))

    elif attempted_download is True:
        prntr.e('Failed to download DRM tools. Please report this error.')


def setup_user_auth(prntr, args, conf):
    # 1) load CLI parameters
    ebook_home = args.ebook_home
    username = args.username
    password = args.password

    # 2) load ENV vars
    if ebook_home is None:
        ebook_home = os.environ.get('EBOOK_HOME')
    if username is None:
        username = os.environ.get('EBOOK_USER')
    if password is None:
        password = os.environ.get('EBOOK_PASS')

    # 3) load settings from saved config
    if ebook_home is None or len(ebook_home) == 0:
        ebook_home = conf['ebook_home']
    if username is None or len(username) == 0:
        username = conf['username']
    if password is None or len(password) == 0:
        password = conf['password']

    # 4.1) load username via readline
    if username is None or len(username) == 0:
        prntr.p("Please enter your O.G.R.E. username, or press enter to use '{}':".format(getpass.getuser()))
        ri = raw_input()
        if len(ri) > 0:
            username = ri
        else:
            username = getpass.getuser()

        # final username verification
        if username is None or len(username) == 0:
            raise ConfigSetupError('O.G.R.E. username not supplied')

    # 4.2) load password via readline
    if password is None or len(password) == 0:
        prntr.p('Please enter your password, or press enter to exit:')
        password = getpass.getpass()
        if len(password) == 0:
            raise ConfigSetupError('O.G.R.E. password not supplied')

    # return values via conf var
    conf['ebook_home'] = ebook_home
    conf['username'] = username
    conf['password'] = password