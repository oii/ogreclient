from __future__ import absolute_import
from __future__ import unicode_literals

import importlib
import os
import subprocess

from .exceptions import RequestError, DeDrmNotAvailable, DeDrmMissingError, \
        DecryptionError, DecryptionFailed
from .printer import CliPrinter
from .utils import capture, enum, make_temp_directory, OgreConnection

try:
    # import DeDRM libs, capturing anything that's shat out on STDOUT
    with capture() as out:
        moddedrm = importlib.import_module('dedrm.scriptinterface')
    CAN_DECRYPT = True
except ImportError as e:
    CAN_DECRYPT = False


DRM = enum('unknown', 'decrypted', 'none', 'wrong_key', 'failed', 'corrupt')


prntr = CliPrinter.get_printer()


def decrypt(filepath, suffix, config_dir, output_dir=None):
    # use the globally imported dedrm module ..
    global moddedrm

    # .. unless CAN_DECRYPT is false
    if CAN_DECRYPT is False:
        try:
            # attempt dynamic import of dedrm in case it has been installed since original import
            with capture() as out:
                moddedrm = importlib.import_module('dedrm.scriptinterface')
        except ImportError:
            raise DeDrmMissingError

    if os.path.exists(filepath) is False or os.path.isfile(filepath) is False:
        raise DeDrmMissingError

    out = ""

    with make_temp_directory() as ebook_convert_path:
        # attempt to decrypt each book, capturing STDOUT
        with capture() as out:
            if suffix == '.epub':
                moddedrm.decryptepub(filepath, ebook_convert_path, config_dir)
            elif suffix == '.pdb':
                moddedrm.decryptpdb(filepath, ebook_convert_path, config_dir)
            elif suffix in ('.mobi', '.azw', '.azw1', '.azw3', '.azw4', '.tpz'):
                moddedrm.decryptk4mobi(filepath, ebook_convert_path, config_dir)
            elif suffix == '.pdf':
                moddedrm.decryptpdf(filepath, ebook_convert_path, config_dir)

        # decryption state of current book
        state = DRM.unknown

        # handle the various outputs from the different decrypt routines
        if suffix == '.epub':
            for line in out:
                if ' is not DRMed.' in line:
                    state = DRM.none
                    break
                elif 'Decrypted Adobe ePub' in line:
                    state = DRM.decrypted
                    break
                elif 'Could not decrypt' in line and 'Wrong key' in line:
                    state = DRM.wrong_key
                    break
                elif 'Error while trying to fix epub' in line:
                    state = DRM.corrupt
                    break
        elif suffix in ('.mobi', '.azw', '.azw1', '.azw3', '.azw4', '.tpz'):
            for line in out:
                if 'This book is not encrypted.' in line:
                    state = DRM.none
                    break
                elif 'Decryption succeeded' in line:
                    state = DRM.decrypted
                    break
                elif 'DrmException: No key found' in line:
                    state = DRM.wrong_key
                    break
        elif suffix == '.pdf':
            state = DRM.none
            for line in out:
                if 'Error serializing pdf' in line:
                    raise DecryptionFailed(out)

        if state == DRM.decrypted:
            try:
                # find the filename of the newly decrypted ebook
                decrypted_filename = next((
                    f for f in os.listdir(ebook_convert_path) if '_nodrm' in f
                ), None)

                # output_dir as supplied, or current directory
                if output_dir is not None:
                    output_filepath = os.path.join(output_dir, decrypted_filename.replace(' ', '_'))
                else:
                    output_filepath = os.path.join(os.getcwd(), decrypted_filename.replace(' ', '_'))

                # move the decrypted file to the output path
                os.rename(os.path.join(ebook_convert_path, decrypted_filename), output_filepath)

            except Exception as e:
                raise DecryptionError(
                    'Decrypt successful, but failed to locate decrypted file: {}\n{}'.format(e, out)
                )
        else:
            output_filepath = None

    return state, output_filepath


def init_keys(config_dir, ignore_check=False):
    if ignore_check is False and CAN_DECRYPT is False:
        raise DeDrmMissingError

    msgs = []

    # extract the Kindle key
    kindlekeyfile = os.path.join(config_dir, 'kindlekey.k4i')
    if not os.path.exists(kindlekeyfile):
        from dedrm import kindlekey
        with capture() as out:
            kindlekey.getkey(kindlekeyfile)

        for line in out:
            if 'No k4Mac' in line:
                break
            elif 'K4PC' in line:
                msgs.append('Extracted Kindle4PC key')
                break
            elif 'k4Mac' in line:
                msgs.append('Extracted Kindle4Mac key')
                break

    # extract the Adobe key
    adeptkeyfile = os.path.join(config_dir, 'adeptkey.der')
    if not os.path.exists(adeptkeyfile):
        try:
            from dedrm import adobekey
            with capture() as out:
                adobekey.getkey(adeptkeyfile)

            for line in out:
                if 'Saved a key' in line:
                    msgs.append('Extracted Adobe DE key')
                    break
        except adobekey.ADEPTError:
            pass

    return msgs


def download_dedrm(config, debug=False):
    prntr.info('Downloading latest DRM tools from {}'.format(config['host'].netloc))

    # authenticate with ogreserver to get DRM tools
    connection = OgreConnection(config)
    connection.login(config['username'], config['password'])

    prntr.info('Authenticated with Ogreserver')
    prntr.info('Downloading..')

    try:
        # start download
        resp, length = connection.download('download-dedrm')
    except RequestError as e:
        raise DeDrmNotAvailable('Failed getting DeDRM package', inner_excp=e)

    # start progress bar
    if length is None:
        prntr.progressi()
    else:
        prntr.progressf(num_blocks=0, total_size=length)
        i = 0

    # stream to file and report progress
    with open('/tmp/dedrm.tar.gz', 'wb') as f:
        for data in resp.iter_content(chunk_size=4096):
            f.write(data)

            # display progress
            if length is None:
                prntr.progressi()
            else:
                i += 1
                prntr.progressf(num_blocks=i, block_size=4096, total_size=length)

    # end progress bar
    prntr.close()

    try:
        # install DRM tools
        subprocess.check_output('pip install /tmp/dedrm.tar.gz', shell=True)

        # attempt a dynamic load of the newly imported tools
        mod = importlib.import_module('dedrm')

    except subprocess.CalledProcessError as e:
        prntr.error('Failed installing dedrm tools', excp=e if debug else None)
        return False
    except ImportError as e:
        prntr.error('Failed installing dedrm tools', excp=e)
        return False

    prntr.info('Installed dedrm {}'.format(mod.PLUGIN_VERSION))
    return True
