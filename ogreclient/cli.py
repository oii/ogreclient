from __future__ import absolute_import
from __future__ import unicode_literals

import argparse
import logging
import os
import sys

from . import __version__

from .config import read_config
from .core import scan_and_show_stats, sync
from .ebook_obj import EbookObject
from .prereqs import setup_ogreclient
from .printer import CliPrinter
from .providers import PROVIDERS

from .exceptions import OgreException, OgreWarning, ConfigSetupError, \
        AuthDeniedError, AuthError, NoEbooksError, SyncError, UploadError


prntr = CliPrinter.get_printer()


def entrypoint():
    ret = False

    try:
        # quick config load
        conf = read_config()

        # setup and run argparse
        args = parse_command_line(conf)

        # global CLI printer
        CliPrinter.init(log_output=args.debug)

        if args.debug:
            prntr.level = logging.DEBUG

        # log at warning level in quiet mode
        if args.quiet:
            prntr.level = logging.WARNING
            prntr.notimer = True

        # no timer during init command
        if args.mode == 'init':
            prntr.notimer = True

        # run some checks and create some config variables
        conf = setup_ogreclient(args, conf)

        if conf is not None:
            ret = main(conf, args)

    except ConfigSetupError as e:
        prntr.error('Failed setting up ogre', excp=e)
    except OgreWarning as e:
        prntr.error(e)
        ret = 1
    except OgreException as e:
        prntr.error('An exception occurred in ogre', excp=e)
        ret = 1
    except KeyboardInterrupt:
        raise SystemExit('\nExiting gracefully on Ctrl-c')
    finally:
        if prntr is not None:
            # allow the printer to cleanup
            prntr.close()

    # exit with return code
    if type(ret) is bool:
        ret = True if ret == 0 else False
    sys.exit(ret)


def parse_command_line(conf):
    parser = argparse.ArgumentParser(
        description='O.G.R.E. client application'
    )
    subparsers = parser.add_subparsers()

    # print the current sesame version
    parser.add_argument(
        '--version', action='version',
        version='sesame {}'.format(__version__),
        help='Print the current Sesame version')

    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Produce lots of output')
    parent_parser.add_argument(
        '--debug', action='store_true',
        help='Print debug information on error')
    parent_parser.add_argument(
        '--quiet', '-q', action='store_true',
        help="Don't produce any output")
    parent_parser.add_argument(
        '--skip-cache', action='store_true',
        help='Ignore the local cache; useful for debugging')


    # setup parser for init command
    pinit = subparsers.add_parser('init',
        parents=[parent_parser],
        help='Initialise your OGRE client install (contacts OGRE server)',
    )
    pinit.set_defaults(mode='init')


    # setup parser for sync command
    psync = subparsers.add_parser('sync',
        parents=[parent_parser],
        help='Synchronise with the OGRE server',
    )
    psync.set_defaults(mode='sync')

    for p in (psync, pinit):
        p.add_argument(
            '--host',
            help='Override the default server host of oii.ogre.yt')
        p.add_argument(
            '--username', '-u',
            help=('Your O.G.R.E. username. '
                  'You can also set the environment variable $OGRE_USER'))
        p.add_argument(
            '--password', '-p',
            help=('Your O.G.R.E. password. '
                  'You can also set the environment variable $OGRE_PASS'))

    psync.add_argument(
        '--no-drm', action='store_true',
        help="Disable DRM removal during sync; don't install DeDRM tools")
    psync.add_argument(
        '--dry-run', '-d', action='store_true',
        help="Dry run the sync; don't actually upload anything to the server")


    # setup parser for scan command
    pscan = subparsers.add_parser('scan',
        parents=[parent_parser],
        help='Scan your computer for ebooks and see some statistics',
    )
    pscan.set_defaults(mode='scan')


    # set ogreserver params which apply to sync & scan
    for p in (psync, pscan):
        for provider, data in PROVIDERS.iteritems():
            if 'has_{}'.format(provider) in conf:
                p.add_argument(
                    '--ignore-{}'.format(provider), action='store_true',
                    help='Ignore ebooks in {}'.format(data['friendly']))

        p.add_argument(
            '--ebook-home', '-H',
            help=('The directory where you keep your ebooks. '
                  'You can also set the environment variable $OGRE_HOME'))


    # setup parser for dedrm command
    pdedrm = subparsers.add_parser('dedrm',
        parents=[parent_parser],
        help='Strip a single ebook of DRM',
    )
    pdedrm.set_defaults(mode='dedrm')
    pdedrm.add_argument(
        'inputfile',
        help='Ebook to be decrypted')
    pdedrm.add_argument(
        '-O', '--output-dir', default=os.getcwd(),
        help='Extract files into a specific directory')


    # setup parser for info command
    pinfo = subparsers.add_parser('info',
        parents=[parent_parser],
        help="Display an ebook's info",
    )
    pinfo.set_defaults(mode='info')
    pinfo.add_argument(
        'inputfile',
        help='Ebook for which to display info')


    args = parser.parse_args()

    if args.mode == 'sync' and args.verbose and args.quiet:
        parser.error('You cannot specify --verbose and --quiet together!')

    return args


def main(conf, args):
    # setup config for sync
    conf.update({
        'debug': args.debug,
        'skip_cache': args.skip_cache,
        'verbose': True if args.debug is True else args.verbose,
    })

    ret = None

    if args.mode == 'init':
        instructions = [
            'You will need to use Kindle for Mac to download ALL the books manually :/',
            'Then run:',
            '    ogre sync',
        ]
        prntr.info('Getting started:', extra=instructions)

    elif args.mode == 'info':
        # display metadata from a single book
        ret = display_info(conf, args.inputfile)

    elif args.mode == 'dedrm':
        # decrypt a single book
        ret = dedrm_single_ebook(conf, args.inputfile, args.output_dir)

    elif args.mode == 'scan':
        # scan for books and display library stats
        ret = run_scan(conf)

    elif args.mode == 'sync':
        # run ogreclient
        conf['no_drm'] = args.no_drm
        ret = run_sync(conf)

        # print lonely output for quiet mode
        if args.quiet:
            prntr.warning("Sync'd {} ebooks".format(ret))

    return ret


def dedrm_single_ebook(conf, inputfile, output_dir):
    filename, ext = os.path.splitext(inputfile)
    from .dedrm import decrypt, DRM, DecryptionError

    try:
        prntr.info('Decrypting ebook {}'.format(os.path.basename(inputfile)))

        state, decrypted_filepath = decrypt(
            inputfile, ext, conf['config_dir'], output_dir=output_dir
        )
        prntr.info('Book decrypted at:', extra=decrypted_filepath, success=True)

    except DecryptionError as e:
        prntr.info(str(e))
        state = None

    if state == DRM.decrypted:
        return 0
    else:
        return 1


def display_info(conf, filepath):
    ebook_obj = EbookObject(filepath)
    ebook_obj.get_metadata(conf)
    prntr.info('Book meta', extra=ebook_obj.meta)


def run_scan(conf):
    ret = False

    try:
        ret = scan_and_show_stats(conf)

    # print messages on error
    except NoEbooksError:
        prntr.error('No ebooks found. Pass --ebook-home or set $OGRE_HOME.')
    except Exception as e:
        prntr.error('Something went very wrong.', excp=e)

    return ret


def run_sync(conf):
    uploaded_count = 0

    try:
        uploaded_count = sync(conf)

    # print messages on error
    except (AuthError, SyncError, UploadError) as e:
        prntr.error('Something went wrong.', excp=e)
    except AuthDeniedError:
        prntr.error('Permission denied. This is a private system.')
    except NoEbooksError:
        prntr.error('No ebooks found. Pass --ebook-home or set $OGRE_HOME.')
    except Exception as e:
        prntr.error('Something went very wrong.', excp=e)

    return uploaded_count
