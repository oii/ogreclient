from __future__ import absolute_import
from __future__ import unicode_literals

import platform


def test_setup_user_auth_env(setup_user_auth, mock_os_environ_get, client_config):
    # setup mock for os.environ.get()
    def os_environ_get_side_effect(env_var, default=None):
        if env_var == 'OGRE_HOST':
            return 'env_user'
        elif env_var == 'OGRE_USER':
            return 'env_user'
        elif env_var == 'OGRE_PASS':
            return 'env_pass'
        else:
            return default
    mock_os_environ_get.side_effect = os_environ_get_side_effect

    # setup_user_auth() modifies client_config in place
    host, username, password = setup_user_auth(client_config)

    # ensure ENV vars are returned when --params are None
    assert username == 'env_user'
    assert password == 'env_pass'


def test_setup_user_auth_config(setup_user_auth, mock_os_environ_get, client_config):
    # setup mock for os.environ.get()
    mock_os_environ_get.return_value = None

    client_config['username'] = 'client_user'
    client_config['password'] = 'client_pass'

    # setup_user_auth() modifies client_config in place
    host, username, password = setup_user_auth(client_config)

    # ensure saved config var returned when ENV & --params are None
    assert username == 'client_user'
    assert password == 'client_pass'


def test_setup_user_auth_params(setup_user_auth, mock_os_environ_get, mock_raw_input, mock_getpass_getpass, client_config):
    # setup mock for os.environ.get()
    mock_os_environ_get.return_value = None

    # ensure client config vars are ignored
    client_config['username'] = None
    client_config['password'] = None

    # setup mock for raw_input()
    mock_raw_input.return_value = 'manual_user'

    # setup mock for getpass module 
    mock_getpass_getpass.return_value = 'manual_pass'

    # setup_user_auth() modifies client_config in place
    host, username, password = setup_user_auth(client_config)

    # ensure ENV vars are returned when --params passed as None
    assert username == 'manual_user'
    assert password == 'manual_pass'


def test_setup_ebook_home_env(setup_ebook_home, mock_os_environ_get, mock_os_mkdir, client_config):
    # setup mock for os.environ.get()
    def os_environ_get_side_effect(env_var, default=None):
        if env_var in 'OGRE_HOME':
            return 'env_home'
        else:
            return default
    mock_os_environ_get.side_effect = os_environ_get_side_effect

    ebook_home = setup_ebook_home(client_config)

    # ensure ENV vars are returned when --params are None
    assert ebook_home == 'env_home'
    assert not mock_os_mkdir.called


def test_setup_ebook_home_params(setup_ebook_home, mock_os_environ_get, mock_os_mkdir, client_config):
    # setup mock for os.environ.get()
    mock_os_environ_get.return_value = None

    client_config['ebook_home'] = 'client_home'

    ebook_home = setup_ebook_home(client_config)

    # ensure saved config var returned when ENV & --params are None
    assert ebook_home == 'client_home'
    assert not mock_os_mkdir.called


def test_setup_ebook_home_mkdir(setup_ebook_home, mock_os_environ_get, mock_os_mkdir, client_config):
    # setup mock for os.environ.get()
    mock_os_environ_get.return_value = None

    # no ebook_home supplied
    client_config['ebook_home'] = None
    client_config['platform'] = platform.system()

    setup_ebook_home(client_config)

    # ensure mkdir called when no ebook_home specified
    assert mock_os_mkdir.called
