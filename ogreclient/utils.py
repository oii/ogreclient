from __future__ import unicode_literals

import base64
import collections
import contextlib
import functools
import hashlib
import json
import random
import shutil
import string
import sys
import tempfile

import requests
from requests.exceptions import ConnectionError, Timeout

from .printer import CliPrinter
from .exceptions import (OgreException, RequestError, AuthError, AuthDeniedError,
                        OgreserverDownError)


prntr = CliPrinter.get_printer()


class OgreConnection(object):
    session_key = None

    def __init__(self, conf, debug=False):
        self.host = conf['host'].netloc
        self.protocol = 'https' if conf.get('use_ssl', False) else 'http'
        self.debug = debug
        self.ignore_ssl_errors = conf.get('ignore_ssl_errors', False)

        # hide SSL warnings barfed from urllib3
        if self.ignore_ssl_errors:
            requests.packages.urllib3.disable_warnings()

    def login(self, username, password):
        try:
            url = '{}://{}/login'.format(self.protocol, self.host)
            prntr.debug(url)
            # authenticate the user
            resp = requests.post(
                url,
                json={
                    'email': username,
                    'password': password
                },
                verify=not self.ignore_ssl_errors,
                timeout=5
            )
            # 502 in prod means Flask app is down
            if resp.status_code == 502:
                raise OgreserverDownError

            data = resp.json()
        except ConnectionError as e:
            raise OgreserverDownError(inner_excp=e)

        # bad login
        if resp.status_code == 403 or data['meta']['code'] >= 400 and data['meta']['code'] < 500:
            raise AuthDeniedError

        try:
            self.session_key = data['response']['user']['authentication_token']
        except KeyError as e:
            raise AuthError(inner_excp=e)

        return True

    def _init_request(self, endpoint):
        # build correct URL to ogreserver
        url = '{}://{}/api/v1/{}'.format(self.protocol, self.host, endpoint)
        prntr.debug(url)
        headers = {'Ogre-key': self.session_key}
        return url, headers

    def download(self, endpoint):
        # setup URL and request headers
        url, headers = self._init_request(endpoint)

        try:
            # start request with streamed response
            resp = requests.get(
                url, headers=headers, stream=True, verify=not self.ignore_ssl_errors, timeout=5
            )

        except (Timeout, ConnectionError) as e:
            raise OgreserverDownError(inner_excp=e)

        # error handle this bitch
        if resp.status_code != 200:
            raise RequestError(resp.status_code)

        return resp, resp.headers.get('Content-length')

    def upload(self, endpoint, ebook_obj, data=None):
        # setup URL and request headers
        url, headers = self._init_request(endpoint)

        # create file part of multipart POST
        files = {
            'ebook': (ebook_obj.safe_name, open(ebook_obj.path, 'rb'))
        }

        try:
            # upload some files and data as multipart
            resp = requests.post(
                url, headers=headers, data=data, files=files, verify=not self.ignore_ssl_errors, timeout=5
            )

        except (Timeout, ConnectionError) as e:
            raise OgreserverDownError(inner_excp=e)

        # error handle this bitch
        if resp.status_code != 200:
            raise RequestError(resp.status_code)

        # JSON response as usual
        return resp.json()

    def request(self, endpoint, data=None):
        # setup URL and request headers
        url, headers = self._init_request(endpoint)

        try:
            if data is not None:
                # POST with JSON body
                resp = requests.post(
                    url, headers=headers, json=data, verify=not self.ignore_ssl_errors, timeout=5
                )
            else:
                # GET
                resp = requests.get(
                    url, headers=headers, verify=not self.ignore_ssl_errors, timeout=5
                )

        except (Timeout, ConnectionError) as e:
            raise OgreserverDownError(inner_excp=e)

        # error handle this bitch
        if resp.status_code != 200:
            raise RequestError(resp.status_code)

        # replies are always JSON
        return resp.json()


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
                except OgreException as e:
                    last_error = e
                retry += 1

            if last_error is not None:
                raise last_error

        return wrapped
    return decorator


def enum(*sequential, **named):
    enums = dict(zip(sequential, range(len(sequential))), **named)
    return type(str('Enum'), (), enums)


def serialize_defs(definitions):
    return json.dumps([
        [k, v.is_valid_format, v.is_non_fiction]
        for k,v in definitions.iteritems()
    ])

def deserialize_defs(data):
    # namedtuple used for definition entries
    FormatConfig = collections.namedtuple('FormatConfig', ('is_valid_format', 'is_non_fiction'))

    return collections.OrderedDict(
        [(v[0], FormatConfig(v[1], v[2])) for v in data]
    )
