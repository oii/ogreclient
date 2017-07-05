# coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import unicode_literals

import os
import shutil

import pytest


@pytest.mark.requires_calibre
def test_metadata_epub(helper_get_ebook):
    # Frankenstein
    ebook_obj = helper_get_ebook('pg84.epub')
    assert ebook_obj.meta['firstname'] == 'Mary Wollstonecraft'
    assert ebook_obj.meta['lastname'] == 'Shelley'
    assert ebook_obj.meta['title'] == 'Frankenstein'
    assert ebook_obj.meta['uri'] == 'http://www.gutenberg.org/ebooks/84'

    # Beowulf
    ebook_obj = helper_get_ebook('pg16328.epub')
    assert ebook_obj.meta['lastname'] == 'Unknown'
    assert ebook_obj.meta['title'] == 'Beowulf / An Anglo-Saxon Epic Poem'
    assert ebook_obj.meta['uri'] == 'http://www.gutenberg.org/ebooks/16328'

    # Wizard of Oz
    ebook_obj = helper_get_ebook('pg55.epub')
    assert ebook_obj.meta['firstname'] == 'L. Frank (Lyman Frank)'
    assert ebook_obj.meta['lastname'] == 'Baum'
    assert ebook_obj.meta['title'] == 'The Wonderful Wizard of Oz'
    assert ebook_obj.meta['uri'] == 'http://www.gutenberg.org/ebooks/55'
    assert ebook_obj.meta['tags'] == 'Fantasy, Oz (Imaginary place) -- Fiction'


@pytest.mark.requires_calibre
def test_metadata_mobi(helper_get_ebook):
    # Wonderland, converted to mobi
    ebook_obj = helper_get_ebook('pg11.mobi')
    assert ebook_obj.meta['firstname'] == 'Lewis'
    assert ebook_obj.meta['lastname'] == 'Carroll'
    assert ebook_obj.meta['title'] == "Alice's Adventures in Wonderland"
    assert ebook_obj.meta['tags'] == 'Fantasy'
    assert ebook_obj.meta['asin'] == '4373df90-da57-42de-9327-90f0e73e8e45'


@pytest.mark.requires_calibre
def test_metadata_utf8(helper_get_ebook):
    # Wuthering Heights
    ebook_obj = helper_get_ebook('pg768.epub')
    assert ebook_obj.meta['firstname'] == 'Emily'
    assert ebook_obj.meta['lastname'] == 'Brontë'


def test_parse_authortitle(parse_author_method):
    # double-barrelled firstname
    firstname, lastname = parse_author_method('H. C. Andersen')
    for var in (firstname, lastname):
        assert type(var) is unicode
    assert firstname == 'H. C.'
    assert lastname == 'Andersen'

    # UTF-8 encoded lastname (unicode)
    firstname, lastname = parse_author_method('Emily Brontë')
    for var in (firstname, lastname):
        assert type(var) is unicode
    assert firstname == 'Emily'
    assert lastname == 'Brontë'

    # UTF-8 encoded lastname (utf8 byte string)
    firstname, lastname = parse_author_method('Emily Brontë'.encode('utf8'))
    for var in (firstname, lastname):
        assert type(var) is unicode
    assert firstname == 'Emily'
    assert lastname == 'Brontë'

    # comma-separated lastname, firstname
    firstname, lastname = parse_author_method('Carroll, Lewis')
    for var in (firstname, lastname):
        assert type(var) is unicode
    assert firstname == 'Lewis'
    assert lastname == 'Carroll'

    # comma-separated lastname, firstname in appended brackets
    firstname, lastname = parse_author_method('Lewis Carroll [Carroll, Lewis]')
    for var in (firstname, lastname):
        assert type(var) is unicode
    assert firstname == 'Lewis'
    assert lastname == 'Carroll'

    # comma-separated lastname, firstname & double-barrelled firstname
    firstname, lastname = parse_author_method('Andersen, H. C.')
    for var in (firstname, lastname):
        assert type(var) is unicode
    assert firstname == 'H. C.'
    assert lastname == 'Andersen'


@pytest.mark.requires_calibre
def test_metadata_dedrm(helper_get_ebook, ebook_lib_path, tmpdir):
    # stick Alice in Wonderland into a tmpdir
    shutil.copy(os.path.join(ebook_lib_path, 'pg11.epub'), tmpdir.strpath)

    ebook_obj = helper_get_ebook('pg11.epub', basepath=tmpdir.strpath)

    # add DeDRM tag to test epub
    ebook_obj.add_dedrm_tag()

    # verify that ogre_id is on the epub
    ebook_obj.get_metadata()
    assert 'uri' in ebook_obj.meta.keys()
    assert hasattr(ebook_obj, 'drmfree')
    assert 'OGRE-DeDRM' not in ebook_obj.meta['tags']


@pytest.mark.requires_calibre
def test_metadata_ogreid_epub(mock_connection, helper_get_ebook, ebook_lib_path, tmpdir):
    # mock return from urlopen().read()
    mock_connection.request.return_value = {'result': 'ok'}

    # stick Alice in Wonderland into a tmpdir
    shutil.copy(os.path.join(ebook_lib_path, 'pg11.epub'), tmpdir.strpath)

    ebook_obj = helper_get_ebook('pg11.epub', basepath=tmpdir.strpath)

    # add ogre_id to test epub
    ebook_obj.add_ogre_id_tag(
        ebook_id='ëgg',
        connection=mock_connection,
    )

    # verify that ogre_id is on the epub
    metadata = ebook_obj._metadata_extract()
    assert metadata.get('ebook_id') == 'ëgg'
    assert 'ogre_id' not in metadata.get('tags')


@pytest.mark.requires_calibre
def test_metadata_ogreid_mobi(mock_connection, helper_get_ebook, ebook_lib_path, tmpdir):
    # mock return from urlopen().read()
    mock_connection.request.return_value = {'result': 'ok'}

    # stick Alice in Wonderland into a tmpdir
    shutil.copy(os.path.join(ebook_lib_path, 'pg11.mobi'), tmpdir.strpath)

    ebook_obj = helper_get_ebook('pg11.mobi', basepath=tmpdir.strpath)

    # test tags field
    ebook_obj.meta['tags'] = 'Fantasy'

    # add ogre_id to test mobi
    ebook_obj.add_ogre_id_tag(
        ebook_id='ëgg',
        connection=mock_connection,
    )

    # verify that ogre_id is on the mobi
    metadata = ebook_obj._metadata_extract()
    assert metadata.get('ebook_id') == 'ëgg'
    assert metadata.get('tags') == 'Fantasy'
    assert 'ogre_id' not in metadata.get('tags')


@pytest.mark.requires_calibre
def test_metadata_ogreid_pdf(mock_connection, helper_get_ebook, ebook_lib_path, tmpdir):
    # mock return from urlopen().read()
    mock_connection.request.return_value = {'result': 'ok'}

    # stick Alice in Wonderland into a tmpdir
    shutil.copy(os.path.join(ebook_lib_path, 'pg11.pdf'), tmpdir.strpath)

    ebook_obj = helper_get_ebook('pg11.pdf', basepath=tmpdir.strpath)

    # test tags field
    ebook_obj.meta['tags'] = 'Fantasy'

    # add ogre_id to test pdf
    ebook_obj.add_ogre_id_tag(
        ebook_id='ëgg',
        connection=mock_connection,
    )

    # verify that ogre_id is on the pdf
    metadata = ebook_obj._metadata_extract()
    assert metadata.get('ebook_id') == 'ëgg'
    assert metadata.get('tags') == 'Fantasy'
    assert 'ogre_id' not in metadata.get('tags')


@pytest.mark.requires_calibre
def test_metadata_ogreid_azw3(mock_connection, helper_get_ebook, ebook_lib_path, tmpdir):
    # mock return from urlopen().read()
    mock_connection.request.return_value = {'result': 'ok'}

    # stick Alice in Wonderland into a tmpdir
    shutil.copy(os.path.join(ebook_lib_path, 'pg11.azw3'), tmpdir.strpath)

    ebook_obj = helper_get_ebook('pg11.azw3', basepath=tmpdir.strpath)

    # test tags field
    ebook_obj.meta['tags'] = 'Fantasy'

    # add ogre_id to test azw3
    ebook_obj.add_ogre_id_tag(
        ebook_id='ëgg',
        connection=mock_connection,
    )

    # verify that ogre_id is on the azw3
    metadata = ebook_obj._metadata_extract()
    assert metadata.get('ebook_id') == 'ëgg'
    assert metadata.get('tags') == 'Fantasy'
    assert 'ogre_id' not in metadata.get('tags')
