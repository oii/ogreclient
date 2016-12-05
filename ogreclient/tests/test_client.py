from __future__ import absolute_import
from __future__ import unicode_literals

import os
import shutil

from ..ogreclient.providers import LibProvider


def test_search(search_for_ebooks, mock_subprocess_popen, client_config, ebook_lib_path, tmpdir):
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


def test_search_ranking(search_for_ebooks, mock_subprocess_popen, client_config, ebook_lib_path, tmpdir):
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
