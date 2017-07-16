from __future__ import absolute_import
from __future__ import unicode_literals

import os
import platform
import plistlib
import shutil
import subprocess
import urllib
import urlparse

from xml.dom import minidom

from .exceptions import (ProviderBaseError, KindleProviderError, ADEProviderError,
                         ProviderUnavailableBaseWarning, KindleUnavailableWarning,
                         ADEUnavailableWarning, EbookHomeUnavailableWarning)
from .printer import CliPrinter
from .utils import make_temp_directory


prntr = CliPrinter.get_printer()


class ProviderFactory:
    @classmethod
    def create(cls, *args, **kwargs):
        provider = PROVIDERS[args[0]]
        # pass provider friendly name into constructor
        kwargs.update({'friendly': provider['friendly']})
        return provider['class'](**kwargs)

class ProviderBase(object):
    version = None
    needs_scan = True

    def __init__(self, friendly=None, config=None):
        self.friendly = friendly


class LibProvider(ProviderBase):
    '''
    A LibProvider contains a single directory containing ebooks

    Class can be instantiated from config module, which means libpath will be supplied
    to the constructor and scan can be skipped
    '''
    libpath = None

    def __init__(self, friendly=None, libpath=None, config=None):
        super(LibProvider, self).__init__(friendly)

        # store the supplied path, if it exists
        if libpath and os.path.exists(libpath) is True:
            self.libpath = libpath
            self.needs_scan = False

class EbookHomeProvider(LibProvider):
    '''
    A specialised LibsProvider just for $OGRE_HOME
    '''
    def __init__(self, friendly=None, config=None):
        super(EbookHomeProvider, self).__init__(friendly, libpath=config['ebook_home'])

class PathsProvider(ProviderBase):
    '''
    A PathsProvider contains a list of direct ebook paths
    '''
    paths = None


PROVIDERS = {
    'home': {
        'friendly': 'Ebook Home',
        'class': EbookHomeProvider,
    },
    'kindle': {
        'friendly': 'Amazon Kindle',
        'class': LibProvider,
    },
    'ade': {
        'friendly': 'Adobe Digital Editions',
        'class': PathsProvider,
    },
}


def find_ebook_providers(conf, ignore=None):
    '''
    Locate any ebook providers on the client machine (ie. Kindle, ADE)
    '''
    if 'providers' not in conf:
        conf['providers'] = {}

    for provider_name in PROVIDERS.keys():
        # ignore certain providers as determined by --ignore-* params
        if ignore and provider_name in ignore:
            # remove provider loaded from app.config
            if provider_name in conf['providers']:
                conf['providers'][provider_name] = None
            continue

        # initialise any providers which werent loaded from config
        if not conf['providers'].get(provider_name):
            conf['providers'][provider_name] = ProviderFactory.create(provider_name, config=conf)

        # local variable for provider object
        provider = conf['providers'][provider_name]

        found = False

        if provider.needs_scan:
            # call provider handler functions dynamically by platform
            func_name = '_handle_{}_{}'.format(provider_name, platform.system())
            if func_name in globals() and hasattr(globals()[func_name], '__call__'):
                try:
                    globals()[func_name](provider)
                    found = True

                except ProviderUnavailableBaseWarning as e:
                    # print app not installed messaging
                    prntr.debug(e)
                except ProviderBaseError as e:
                    prntr.error('Failed processing {}'.format(provider.friendly), excp=e)
            else:
                prntr.info('{} not supported for {} books. Contact oii.'.format(platform.system(), provider.friendly))
        else:
            found = True

        if found is True:
            prntr.info('Found {} directory'.format(provider.friendly))
        else:
            # provider is unavailable; remove it from the config
            conf['providers'][provider_name] = None


def _handle_home_Darwin(provider):
    # if OGRE_HOME is not set, just skip
    if not provider.libpath:
        raise EbookHomeUnavailableWarning


def _handle_kindle_Darwin(provider):
    try:
        # extract Kindle version
        provider.version = plistlib.readPlist('/Applications/Kindle.app/Contents/Info.plist')['CFBundleShortVersionString']
    except (IOError, KeyError) as e:
        raise KindleUnavailableWarning('Kindle for Mac not installed')

    # search for Kindle prefs on OSX
    plists = [
        os.path.expanduser('~/Library/Containers/com.amazon.Kindle/Data/Library/Preferences/com.amazon.Kindle.plist'),
        os.path.expanduser('~/Library/Preferences/com.amazon.Kindle.plist'),
    ]

    inner_excp = None

    # check OSX plist file exists
    for plist in plists:
        if not os.path.exists(plist):
            continue

        with make_temp_directory() as tmpdir:
            try:
                # parse plist file and extract Kindle's file storage directory
                plist_tmp_path = os.path.join(tmpdir, 'com.amazon.Kindle.plist')

                # copy plist to temp dir
                shutil.copyfile(plist, plist_tmp_path)

                # convert binary plist file to XML
                subprocess.check_call('plutil -convert xml1 {}'.format(plist_tmp_path), shell=True)

                # extract plist
                data = plistlib.readPlist(plist_tmp_path)

                # validate kindle dir
                if os.path.exists(data['User Settings.CONTENT_PATH']):
                    provider.libpath = data['User Settings.CONTENT_PATH']

            except Exception as e:
                inner_excp = KindleProviderError(inner_excp=e)

    if provider.libpath is None:
        raise KindleUnavailableWarning(
            'Kindle for Mac is installed, but not setup yet',
            inner_excp=inner_excp
        )


def _handle_ade_Darwin(provider):
    # search for ADE on OSX
    manifest_path = os.path.expanduser('~/Documents/Digital Editions')

    # check OSX ADE path exists
    if not os.path.exists(manifest_path):
        raise ADEUnavailableWarning('Adobe Digital Editions not installed')

    try:
        def parse_manifest(path):
            # parse XML plist file
            with open(path, 'r') as f:
                data = f.read()

            # minidom is rubbish; but there's no nextSibling in ElementTree
            dom = minidom.parseString(data)
            el = next(iter(dom.getElementsByTagName('dp:content')), None)

            if el is not None:
                p = urlparse.urlparse(el.getAttribute('href'))
                return urllib.unquote(
                    os.path.abspath(os.path.join(p.netloc, p.path))
                )

        provider.paths = []

        for root, _, files in os.walk(manifest_path):
            for filename in files:
                if filename.endswith('.xml'):
                    path = parse_manifest(os.path.join(root, filename))
                    if path is not None and os.path.exists(path):
                        provider.paths.append(
                            (path, os.path.splitext(path)[1][1:])
                        )

    except Exception as e:
        raise ADEProviderError(inner_excp=e)
