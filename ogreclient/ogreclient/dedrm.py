from __future__ import absolute_import

import os

from . import OgreError
from .utils import capture, enum

try:
    # import DeDRM libs, capturing anything that's shat out on STDOUT
    with capture() as out:
        from dedrm.scriptinterface import decryptepub, decryptpdf, decryptpdb, decryptk4mobi
    CAN_DECRYPT = True
except ImportError:
    CAN_DECRYPT = False


DRM = enum('unknown', 'decrypted', 'none', 'wrong_key', 'failed', 'corrupt')


def decrypt(filepath, suffix, ebook_convert_path, config_dir, output_dir=None):
    if CAN_DECRYPT is False:
        raise DeDrmMissingError

    if os.path.exists(filepath) is False or os.path.isfile(filepath) is False:
        raise DeDrmMissingError

    out = ""

    # attempt to decrypt each book, capturing STDOUT
    with capture() as out:
        if suffix == '.epub':
            decryptepub(filepath, ebook_convert_path, config_dir)
        elif suffix == '.pdb':
            decryptpdb(filepath, ebook_convert_path, config_dir)
        elif suffix in ('.mobi', '.azw', '.azw1', '.azw3', '.azw4', '.tpz'):
            decryptk4mobi(filepath, ebook_convert_path, config_dir)
        elif suffix == '.pdf':
            decryptpdf(filepath, ebook_convert_path, config_dir)

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
                state = DRM.failed
                break

    if state == DRM.decrypted:
        try:
            # get the filename of the newly decrypted ebook
            decrypted_filename = [
                f for f in os.listdir(ebook_convert_path) if '_nodrm' in f
            ][0]

            # replace spaces with underscores
            output_filename = decrypted_filename.replace(' ', '_')

            # move the decrypted file to the output path
            if output_dir is not None and state == DRM.decrypted:
                os.rename(
                    os.path.join(ebook_convert_path, decrypted_filename),
                    os.path.join(output_dir, output_filename)
                )

        except Exception as e:
            # TODO debug mode includes stacktraces
            raise DecryptionError(
                'Decrypt successful, but failed to locate decrypted file: {}\n{}'.format(e, out)
            )
    else:
        output_filename = None

    return state, output_filename


class DeDrmMissingError(OgreError):
    pass

class DecryptionError(OgreError):
    pass