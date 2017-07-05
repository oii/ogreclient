from __future__ import absolute_import
from __future__ import unicode_literals

import ConfigParser
import json
import os
import platform
from urlparse import urlunparse

from .providers import PROVIDERS, ProviderFactory
from .utils import serialize_defs, deserialize_defs


def _get_config_dir():
    # setup config dir path
    if platform.system() == 'Windows':
        config_dir = '~'
    else:
        config_dir = '~/.config'
    return os.path.join(os.environ.get('XDG_CONFIG_HOME', os.path.expanduser(config_dir)), 'ogre')


def write_config(conf):
    cp = ConfigParser.RawConfigParser()

    # general config section
    cp.add_section('config')
    if 'calibre_ebook_meta_bin' in conf:
        cp.set('config', 'calibre_ebook_meta_bin', conf['calibre_ebook_meta_bin'])

    # ogreserver specific section
    if 'host' in conf or 'username' in conf or 'password' in conf:
        cp.add_section('ogreserver')
        if 'host' in conf:
            cp.set('ogreserver', 'host', urlunparse(conf['host']))
        if 'username' in conf:
            cp.set('ogreserver', 'username', conf['username'])
        if 'password' in conf:
            cp.set('ogreserver', 'password', conf['password'])

    # create sections for each provider
    for provider in PROVIDERS.keys():
        if provider in conf['providers']:
            cp.add_section(provider)

    # provider specific config
    if conf['providers']['kindle']:
        cp.set('kindle', 'libpath', conf['providers']['kindle'].libpath)

    # store ebook scan definitions
    if 'definitions' in conf:
        cp.add_section('definitions')
        cp.set('definitions', 'definitions', serialize_defs(conf['definitions']))

    with open(os.path.join(conf['config_dir'], 'app.config'), 'wb') as f_config:
        cp.write(f_config)


def read_config():
    conf = {'config_dir': _get_config_dir(), 'providers': {}}

    if not os.path.exists(conf['config_dir']):
        os.makedirs(conf['config_dir'])
        return conf

    if not os.path.exists(os.path.join(conf['config_dir'], 'app.config')):
        return conf

    cp = ConfigParser.RawConfigParser()

    try:
        cp.read(os.path.join(conf['config_dir'], 'app.config'))
    except ConfigParser.ParsingError:
        # abort if config is broken
        return conf

    # read the user/pass/host variables first
    conf['host'] = cp.get('ogreserver', 'host')
    conf['username'] = cp.get('ogreserver', 'username')
    conf['password'] = cp.get('ogreserver', 'password')

    try:
        conf['calibre_ebook_meta_bin'] = cp.get('config', 'calibre_ebook_meta_bin')
    except ConfigParser.NoSectionError:
        # if calibre config not set, return early. In this case it's likely
        # app.config has been created externally by a script
        return conf

    # extract which providers are already known (used for CLI options)
    for provider in PROVIDERS.keys():
        if cp.has_section(provider):
            conf['has_{}'.format(provider)] = True

    # provider specific config
    if cp.has_section('kindle'):
        try:
            conf['providers']['kindle'] = ProviderFactory.create(
                'kindle', libpath=cp.get('kindle', 'libpath')
            )
        except ConfigParser.NoOptionError:
            conf['providers']['kindle'] = None

    # load ebook scan definitions
    conf['definitions'] = deserialize_defs(
        json.loads(cp.get('definitions', 'definitions'))
    )

    return conf
