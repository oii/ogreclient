from __future__ import unicode_literals

import base64
import contextlib
import functools
import hashlib
import random
import shutil
import string
import sys
import tempfile

from ogreclient import exceptions
from ogreclient.utils.printer import CliPrinter


prntr = CliPrinter.get_printer()


def compute_md5(filepath, buf_size=524288):
    """
    Adapted from boto/utils.py

    Compute MD5 hash on passed file and return results in a tuple of values.

    :type fp: file
    :param fp: File pointer to the file to MD5 hash.  The file pointer
               will be reset to the beginning of the file before the
               method returns.

    :type buf_size: integer
    :param buf_size: Number of bytes per read request.

    :rtype: tuple
    :return: A tuple containing the hex digest version of the MD5 hash
             as the first element, the base64 encoded version of the
             plain digest as the second element and the file size as
             the third element.
    """
    fp = open(filepath, "rb")
    try:
        m = hashlib.md5()
        fp.seek(0)
        s = fp.read(buf_size)
        while s:
            m.update(s)
            s = fp.read(buf_size)

        hex_md5 = m.hexdigest()
        base64md5 = base64.encodestring(m.digest())

        if base64md5[-1] == '\n':
            base64md5 = base64md5[0:-1]

        file_size = fp.tell()
        fp.seek(0)
        return (hex_md5, base64md5, file_size)

    finally:
        fp.close()


@contextlib.contextmanager
def make_temp_directory():
    temp_dir = tempfile.mkdtemp()
    try:
        yield unicode(temp_dir)
    except Exception as e:
        raise e
    finally:
        shutil.rmtree(temp_dir)


def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))


@contextlib.contextmanager
def capture():
    """
    Capture stdout/stderr into a string
    http://stackoverflow.com/a/10743550/425050
    """
    import codecs
    from cStringIO import StringIO
    oldout, olderr = sys.stdout, sys.stderr
    try:
        out = [
            codecs.getwriter('utf8')(StringIO()),
            codecs.getwriter('utf8')(StringIO()),
        ]
        sys.stdout, sys.stderr = out
        yield out
    finally:
        sys.stdout, sys.stderr = oldout, olderr
        out[0] = out[0].getvalue().decode('utf-8')
        out[1] = out[1].getvalue().decode('utf-8')


def retry(times):
    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            """
            Retry method $times number of times.

            - Expects OgreExceptions to indicate called method failure.
            - The most recent OgreException is re-raised if no success.
            """
            retry = 0

            while retry < times:
                last_error = None
                try:
                    f(*args, **kwargs)
                    break
                except exceptions.OgreException as e:
                    last_error = e
                retry += 1

            if last_error is not None:
                raise last_error

        return wrapped
    return decorator


def enum(*sequential, **named):
    enums = dict(zip(sequential, range(len(sequential))), **named)
    return type(str('Enum'), (), enums)
