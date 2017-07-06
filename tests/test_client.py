from __future__ import absolute_import
from __future__ import unicode_literals

import collections
import os
import shutil

import mock

from ogreclient.providers import LibProvider


@mock.patch('ogreclient.utils.OgreConnection')
def test_get_definitions(mock_connection, get_definitions, client_config):
    # /definitions endpoint returns json of app's EBOOK_DEFINITIONS config
    mock_connection.request.return_value = [
        ['mobi', True, False],
        ['pdf', False, True],
        ['azw', False, True],
        ['azw3', True, False],
        ['epub', True, False]
    ]
    defs = get_definitions(mock_connection)

    assert type(defs) is collections.OrderedDict

    # ensure mobi is primary format, azw3 is second
    assert defs.keys()[0] == 'mobi'
    assert defs['mobi'].is_valid_format is True
    assert defs.keys()[1] == 'pdf'
    assert defs['pdf'].is_valid_format is False


@mock.patch('ogreclient.ebook_obj.subprocess.Popen')
def test_search(mock_subprocess_popen, search_for_ebooks, client_config, ebook_lib_path, tmpdir):
    # mock return from Popen().communicate()
    mock_subprocess_popen.return_value.communicate.return_value = (b"Title               : Alice's Adventures in Wonderland\nAuthor(s)           : Lewis Carroll [Carroll, Lewis]\nTags                : Fantasy\nLanguages           : eng\nPublished           : 2008-06-26T14:00:00+00:00\nRights              : Public domain in the USA.\nIdentifiers         : uri:http://www.gutenberg.org/ebooks/11\n", b'')

    # setup ebook home for this test
    ebook_home_provider = LibProvider(libpath=tmpdir.strpath)
    client_config['providers']['ebook_home'] = ebook_home_provider

    # stick Alice in Wonderland into ebook_home
    shutil.copy(os.path.join(ebook_lib_path, 'pg11.epub'), tmpdir.strpath)

    # search for ebooks
    data, errord = search_for_ebooks(client_config)

    # verify found book
    assert len(data) == 1
    assert data.keys()[0] == "Lewis\u0006Carroll\u0007Alice's Adventures in Wonderland"
    assert data[data.keys()[0]].file_hash == '42344f0e247923fcb347c0e5de5fc762'


@mock.patch('ogreclient.ebook_obj.subprocess.Popen')
def test_search_ranking(mock_subprocess_popen, search_for_ebooks, client_config, ebook_lib_path, tmpdir):
    # mock return from Popen().communicate()
    mock_subprocess_popen.return_value.communicate.return_value = (b"Title               : Alice's Adventures in Wonderland\nAuthor(s)           : Lewis Carroll [Carroll, Lewis]\nTags                : Fantasy\nLanguages           : eng\nPublished           : 2008-06-26T14:00:00+00:00\nRights              : Public domain in the USA.\nIdentifiers         : uri:http://www.gutenberg.org/ebooks/11\n", b'')

    # setup ebook home for this test
    ebook_home_provider = LibProvider(libpath=tmpdir.strpath)
    client_config['providers']['ebook_home'] = ebook_home_provider

    # stick Alice in Wonderland epub & mobi into ebook_home
    for book in ('pg11.epub', 'pg11.mobi'):
        shutil.copy(os.path.join(ebook_lib_path, book), tmpdir.strpath)

    # search for ebooks
    data, errord = search_for_ebooks(client_config)

    # verify found mobi file hash; it is ranked higher than epub
    assert len(data) == 1
    assert data[data.keys()[0]].file_hash == 'f2cb3defc99fc9630722677843565721'
