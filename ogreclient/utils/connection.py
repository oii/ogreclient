from __future__ import unicode_literals

from ogreclient import exceptions
from ogreclient.utils.printer import CliPrinter

import requests
from requests.exceptions import ConnectionError, Timeout


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
                raise exceptions.OgreserverDownError

            data = resp.json()
        except ConnectionError as e:
            raise exceptions.OgreserverDownError(inner_excp=e)

        # bad login
        if resp.status_code == 403 or data['meta']['code'] >= 400 and data['meta']['code'] < 500:
            raise exceptions.AuthDeniedError

        try:
            self.session_key = data['response']['user']['authentication_token']
        except KeyError as e:
            raise exceptions.AuthError(inner_excp=e)

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
            raise exceptions.OgreserverDownError(inner_excp=e)

        # error handle this bitch
        if resp.status_code != 200:
            raise exceptions.RequestError(resp.status_code)

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
            raise exceptions.OgreserverDownError(inner_excp=e)

        # error handle this bitch
        if resp.status_code != 200:
            raise exceptions.RequestError(resp.status_code)

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
            raise exceptions.OgreserverDownError(inner_excp=e)

        # error handle this bitch
        if resp.status_code != 200:
            raise exceptions.RequestError(resp.status_code)

        # replies are always JSON
        return resp.json()
