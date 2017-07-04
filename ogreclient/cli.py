from __future__ import absolute_import
from __future__ import unicode_literals

import json
import logging
import os
import sys

import click
click.disable_unicode_literals_warning = True

from ogreclient import exceptions
from ogreclient.config import read_config
from ogreclient.core import scan_and_show_stats, sync as core_sync
from ogreclient.dedrm import decrypt, DRM
from ogreclient.ebook_obj import EbookObject
from ogreclient import prereqs
from ogreclient.printer import CliPrinter
from ogreclient.providers import PROVIDERS


prntr = CliPrinter.get_printer()


class OgreArgs(object):
    def __init__(self, verbose, debug, quiet):
        self.verbose = verbose
        self.debug = debug
        self.quiet = quiet

        # debug implies verbose
        if debug:
            self.verbose = True

    def to_dict(self):
        return {
            'verbose': self.verbose,
            'debug': self.debug,
            'quiet': self.quiet,
        }


@click.group()
@click.version_option()
@click.option('--verbose', '-v', is_flag=True,
              help='Produce lots of output')
@click.option('--debug', '-d', is_flag=True,
              help='Display debug logging')
@click.option('--quiet', '-q', is_flag=True,
              help="Don't produce any output")
@click.pass_context
def cli(ctx, verbose=False, debug=False, quiet=False):
    """
    O.G.R.E. client application
    """
    if verbose and quiet:
        raise click.UsageError('You cannot specify --verbose and --quiet together!')

    # global CLI printer
    CliPrinter.init(log_output=debug)

    if debug:
        prntr.level = logging.DEBUG

    # log at warning level in quiet mode
    if quiet:
        prntr.level = logging.WARNING
        prntr.notimer = True

    # Entrypoint for click application
    ctx.obj = OgreArgs(verbose=verbose, debug=debug, quiet=quiet)


def entrypoint2():
    ret = False

    try:


        if conf is not None:
            ret = main(conf, args)

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


# # set ogreserver params which apply to sync & scan
# for p in (psync, pscan):
#     for provider, data in PROVIDERS.items():
#         if 'has_{}'.format(provider) in conf:
#             p.add_argument(
#                 '--ignore-{}'.format(provider), action='store_true',
#                 help='Ignore ebooks in {}'.format(data['friendly']))


@cli.command()
@click.option('--host', help='Override the default server host of oii.ogre.yt')
@click.option('--username', '-u',
              help='Your O.G.R.E. username. You can also set the environment variable $OGRE_USER')
@click.option('--password', '-p',
              help='Your O.G.R.E. password. You can also set the environment variable $OGRE_PASS')
@click.pass_obj
def init(cargs, host=None, username=None, password=None):
    '''
    Initialise your OGRE client install (checks into OGRE server)
    '''
    # no timer during init command
    prntr.notimer = True

    # run some checks and setup application
    prereqs.setup_ogreclient(
        host=host,
        username=username,
        password=password,
    )

    instructions = [
        'You will need to use Kindle for Mac to download ALL the books manually :/',
        'Then run:',
        '    ogre sync',
    ]
    prntr.info('Getting started:', extra=instructions)


@cli.command()
@click.argument('filepath', type=click.Path(exists=True, dir_okay=False, readable=True))
@click.option('--output-dir', '-O', help='Extract files into a specific directory')
@click.pass_obj
def dedrm(cargs, filepath, output_dir=None):
    '''
    FILEPATH - Ebook to be decrypted
    '''
    # run some checks and setup application
    conf = prereqs.setup_ogreclient()

    _, ext = os.path.splitext(filepath)

    try:
        prntr.info('Decrypting ebook {}'.format(os.path.basename(filepath)))

        state, decrypted_filepath = decrypt(
            filepath, ext, conf['config_dir'], output_dir=output_dir
        )
        prntr.info('Book decrypted at:', extra=decrypted_filepath, success=True)

    except exceptions.DecryptionError as e:
        prntr.info(str(e))
        state = None

    if state == DRM.decrypted:
        return 0
    else:
        return 1


@cli.command()
@click.argument('filepath', type=click.Path(exists=True, dir_okay=False, readable=True))
@click.pass_obj
def info(cargs, filepath):
    '''
    Display an ebook's info

    FILEPATH - Ebook for which to display info
    '''
    # get the current filesystem encoding
    fs_encoding = sys.getfilesystemencoding()

    conf = read_config()

    ebook_obj = EbookObject(conf, filepath.decode(fs_encoding))
    ebook_obj.get_metadata()
    prntr.info('Book meta', extra=json.dumps(ebook_obj.meta, indent=2))


@cli.command()
@click.option('--host', help='Override the default server host of oii.ogre.yt')
@click.option('--username', '-u',
              help='Your O.G.R.E. username. You can also set the environment variable $OGRE_USER')
@click.option('--password', '-p',
              help='Your O.G.R.E. password. You can also set the environment variable $OGRE_PASS')
@click.option('--ebook-home', '-H', type=click.Path(exists=True, file_okay=False, readable=True),
              help=('The directory where you keep your ebooks. '
                    'You can also set the environment variable $OGRE_HOME'))
@click.option('--skip-cache', is_flag=True,
              help='Ignore the local cache (useful for debugging)')
@click.pass_obj
def scan(cargs, host=None, username=None, password=None, ebook_home=None, skip_cache=False):
    '''
    Scan your computer for ebooks and see some statistics
    '''
    # run some checks and setup application
    conf = prereqs.setup_ogreclient(
        host=host,
        username=username,
        password=password,
        ebook_home=ebook_home,
    )

    # merge CLI params into config object
    conf.update(cargs.to_dict())
    conf['skip_cache'] = skip_cache

    ret = False

    try:
        ret = scan_and_show_stats(conf)

    # print messages on error
    except exceptions.NoEbooksError:
        prntr.error('No ebooks found. Pass --ebook-home or set $OGRE_HOME.')
    except Exception as e:
        prntr.error('Something went very wrong.', excp=e)

    return ret


@cli.command()
@click.option('--host', help='Override the default server host of oii.ogre.yt')
@click.option('--username', '-u',
              help='Your O.G.R.E. username. You can also set the environment variable $OGRE_USER')
@click.option('--password', '-p',
              help='Your O.G.R.E. password. You can also set the environment variable $OGRE_PASS')
@click.option('--ebook-home', '-H', type=click.Path(exists=True, file_okay=False, readable=True),
              help=('The directory where you keep your ebooks. '
                    'You can also set the environment variable $OGRE_HOME'))
@click.option('--skip-cache', is_flag=True,
              help='Ignore the local cache (useful for debugging)')
@click.option('--no-drm', is_flag=True,
              help="Disable DRM removal during sync; don't install DeDRM tools")
@click.option('--dry-run', '-d', is_flag=True,
              help="Dry run the sync; don't actually upload anything to the server")
@click.pass_obj
def sync(cargs, host=None, username=None, password=None, ebook_home=None, skip_cache=False, no_drm=False, dry_run=False):
    '''
    Synchronise with the OGRE server
    '''
    # run some checks and setup application
    conf = prereqs.setup_ogreclient(
        host=host,
        username=username,
        password=password,
        ebook_home=ebook_home,
    )

    # merge CLI params into config object
    conf.update(cargs.to_dict())
    conf['skip_cache'] = skip_cache
    conf['no_drm'] = no_drm
    conf['dry_run'] = dry_run

    uploaded_count = 0

    try:
        uploaded_count = core_sync(conf)

    # print messages on error
    except (exceptions.AuthError, exceptions.SyncError, exceptions.UploadError) as e:
        prntr.error('Something went wrong.', excp=e)
    except exceptions.AuthDeniedError:
        prntr.error('Permission denied. This is a private system.')
    except exceptions.NoEbooksError:
        prntr.error('No ebooks found. Pass --ebook-home or set $OGRE_HOME.')
    except Exception as e:
        prntr.error('Something went very wrong.', excp=e)

    # print lonely output for quiet mode
    if cargs.quiet:
        prntr.warning("Sync'd {} ebooks".format(uploaded_count))


    return uploaded_count


# entrypoint for pyinstaller
if __name__ == '__main__':
    cli()
