from __future__ import absolute_import
from __future__ import division

import datetime
import json
import os
import shutil
import subprocess

import urllib
import urllib2
from urllib2 import HTTPError, URLError
from .urllib2_file import newHTTPHandler

from .utils import compute_md5
from .utils import id_generator
from .utils import make_temp_directory
from .printer import CliPrinter, DummyPrinter
from .dedrm import decrypt, DRM

from .exceptions import AuthDeniedError, AuthError, NoEbooksError, NoUploadsError
from .exceptions import BaconError, MushroomError, SpinachError, CorruptEbookError
from .exceptions import FailedWritingMetaDataError, FailedConfirmError


OGRESERVER = "ogre.oii.yt"

# ranked ebook formats
EBOOK_FORMATS = {
    'mobi': 1,
    'azw': 2,
    'azw3': 3,
    'azw4': 4,
    'pdf': 5,
    'epub': 6,
    'pdb': 7,
    'azw1': 8,
    'tpz': 9,
}


def authenticate(host, username, password):
    try:
        # authenticate the user; retrieve an session_key for subsequent requests
        params = urllib.urlencode({
            'username': username,
            'password': password
        })
        req = urllib2.Request(url='http://{}/auth'.format(host), data=params)
        f = urllib2.urlopen(req)
        return f.read()

    except HTTPError as e:
        if e.getcode() == 403:
            raise AuthDeniedError
        else:
            raise AuthError(str(e))
    except URLError as e:
        raise AuthError(str(e))


def sync(config):
    # load the user's database of previously scanned ebooks
    if os.path.exists(config['ebook_cache_path']):
        with open(config['ebook_cache_path'], "r") as f:
            data = f.read()

    # setup temporary cache path
    ebook_cache_temp_path = os.path.join(
        config['config_dir'],
        '{}.tmp'.format(config['ebook_cache_path'])
    )

    # authenticate user and generate session API key
    session_key = authenticate(config['host'], config['username'], config['password'])

    ebooks = []

    if config['quiet'] is True:
        prntr = DummyPrinter()
    else:
        prntr = CliPrinter(start=datetime.datetime.now(), debug=config['debug'])

    # let the user know something is happening
    prntr.p("Searching for ebooks.. ", nonl=True)

    # a relatively quick search for all ebooks
    for root, dirs, files in os.walk(config['ebook_home']):
        for filename in files:
            # TODO use timeit; compare to fnmatch.filter
            fn, ext = os.path.splitext(filename)
            if ext[1:] in EBOOK_FORMATS.keys() and fn[0:2] != '._':
                filepath = os.path.join(root, filename)
                md5_tup = compute_md5(filepath)
                ebooks.append(
                    (filepath, fn, ext, md5_tup[2], md5_tup[0])
                )

    i = 0
    total = len(ebooks)
    prntr.p("Discovered {0} files".format(total))
    if total == 0:
        raise NoEbooksError()

    prntr.p("Scanning ebook meta data and checking DRM..")
    #update_progress(0, length=PROGBAR_LEN)
    ebooks_dict = {}

    # write good ebooks into the local ogre cache to skip DRM test next run
    with open(ebook_cache_temp_path, 'w') as f_ogre_cache:

        # now parse all book meta data; building a complete dataset
        for item in ebooks:
            try:
                # decrypt into a temp path
                with make_temp_directory() as ebook_convert_path:
                    state, out = decrypt(item[0], item[2], ebook_convert_path, config['config_dir'])

                if config['verbose']:
                    if state == DRM.none:
                        prntr.p("{0}".format(item[0]), CliPrinter.NONE)
                    elif state == DRM.decrypted:
                        prntr.p("{0}".format(item[0]), CliPrinter.DEDRM, success=True)
                    elif state == DRM.wrong_key:
                        prntr.e("{0}".format(item[0]), CliPrinter.WRONG_KEY)
                    elif state == DRM.failed:
                        prntr.e("{0}".format(item[0]), CliPrinter.DEDRM,
                            extra=' '.join([l.strip() for l in out])
                        )
                    elif state == DRM.corrupt:
                        prntr.e("{0}".format(item[0]), CliPrinter.CORRUPT)
                    else:
                        prntr.p("{0}\t{1}".format(item[0], out), CliPrinter.UNKNOWN)

            except Exception as e:
                prntr.e("Fatal Exception on {0}".format(item[0]), excp=e)
                continue

            try:
                # extract and parse ebook metadata
                meta = metadata_extract(config['calibre_ebook_meta_bin'], item[0])
            except CorruptEbookError as e:
                # skip books which can't have metadata extracted
                if config['verbose']:
                    prntr.e("{}{}".format(item[1], item[2]), CliPrinter.CORRUPT)
                    continue

            # books are indexed by "authortitle" to handle multiple copies of the same book
            authortitle = "{0} - {1}".format(meta['author'], meta['title'])

            # check for duplicates
            if authortitle in ebooks_dict.keys() and item[2] in ebooks_dict[authortitle].keys():
                # TODO warn user on error stack
                pass
            else:
                # write file path to ogre cache
                # TODO move this to where the ogre_id gets confirmed
                f_ogre_cache.write("%s\n" % item[0])

                # another format of same book found
                write = False

                if authortitle in ebooks_dict.keys():
                    # compare the rank of the format already found against this one
                    existing_rank = EBOOK_FORMATS[ebooks_dict[authortitle]['format']]
                    new_rank = EBOOK_FORMATS[item[2][1:]]

                    # lower is better
                    if new_rank < existing_rank:
                        write = True

                    # upload in favoured formats: mobi, azw, pdf, epub
                    #if ebooks_dict[authortitle]['format'] == "epub" and item[2][1:] in ('mobi', 'azw3', 'azw', 'pdf'):
                    #    write = True
                    #elif ebooks_dict[authortitle]['format'] == "pdf" and item[2][1:] in ('mobi', 'azw3', 'azw'):
                    #    write = True
                    #elif ebooks_dict[authortitle]['format'] == "pdf" and item[2][1:] in ('mobi', 'azw3'):
                    #    write = True
                    #elif ebooks_dict[authortitle]['format'] == "awz" and item[2][1:] in ('mobi'):
                    #    write = True
                else:
                    # new book found
                    write = True

                if write:
                    ebooks_dict[authortitle] = {
                        'path': item[0],
                        'filename': item[1],
                        'format': item[2][1:],
                        'size': item[3],
                        'file_md5': item[4],
                        'owner': config['username'],
                    }
                    # merge all the meta data constructed above
                    ebooks_dict[authortitle].update(meta)

            i += 1
            #update_progress(float(i) / float(total), length=PROGBAR_LEN)

    prntr.p("\nFound {0} ebooks".format(len(ebooks_dict)))

    if len(ebooks_dict) == 0:
        return {}

    # move the temp cache onto the real ogre cache
    statinfo = os.stat(ebook_cache_temp_path)
    if statinfo.st_size > 0:
        os.rename(ebook_cache_temp_path, config['ebook_cache_path'])

    prntr.p("Come on sucker, lick my battery")

    try:
        # post the json array of ebook data
        params = urllib.urlencode({
            'ebooks': json.dumps(ebooks_dict),
            'total': total
        })
        req = urllib2.Request(
            url='http://{0}/post/{1}'.format(
                config['host'],
                urllib.quote_plus(session_key)
            )
        )
        req.add_data(params)
        resp = urllib2.urlopen(req)
        data = resp.read()

        response = json.loads(data)

    except ValueError as e:
        raise BaconError(str(e))
    except (HTTPError, URLError) as e:
        raise MushroomError(str(e))

    # display server messages
    for msg in response['messages']:
        if len(msg) == 2:
            prntr.p("{0} {1}".format(msg[0], msg[1]), CliPrinter.RESPONSE)
        else:
            prntr.p(msg, CliPrinter.RESPONSE)

    if len(response['ebooks_to_upload']) == 0:
        raise NoUploadsError()

    # grammatically correct messages are nice
    plural = "s" if len(response['ebooks_to_upload']) > 1 else ""

    prntr.p("Uploading {0} file{1}. Go make a brew.".format(len(response['ebooks_to_upload']), plural))

    # update any books with ogre_id supplied from ogreserver
    for md5, item in response['ebooks_to_update'].items():
        # find this book in the scan data
        for authortitle in ebooks_dict.keys():
            if md5 == ebooks_dict[authortitle]['file_md5']:
                try:
                    add_ogre_id_to_ebook(
                        config['calibre_ebook_meta_bin'],
                        md5,
                        ebooks_dict[authortitle]['path'],
                        ebooks_dict[authortitle]['format'],
                        item['ebook_id'],
                        config['host'],
                        session_key,
                    )
                    if config['verbose']:
                        prntr.p('Wrote OGRE_ID to {}'.format(ebooks_dict[authortitle]['path']))

                except (FailedWritingMetaDataError, FailedConfirmError) as e:
                    prntr.e('Failed saving OGRE_ID in source ebook', excp=e)

    # upload each requested by the server
    for upload in response['ebooks_to_upload']:
        # iterate all user's found books
        for authortitle in ebooks_dict.keys():
            if upload['file_md5'] == ebooks_dict[authortitle]['file_md5']:
                try:
                    data = upload_single_book(
                        config['host'],
                        session_key,
                        ebooks_dict[authortitle]['path'],
                        upload,
                    )
                    prntr.p(data)

                except SpinachError as e:
                    prntr.e('Failed uploading {}'.format(ebooks_dict[authortitle]['path']), excp=e)

    return True


def upload_single_book(host, session_key, filepath, upload_obj):
    try:
        with open(filepath, "rb") as f:
            # configure for uploads
            opener = urllib2.build_opener(newHTTPHandler())

            # build the post params
            params = {
                'ebook_id': upload_obj['ebook_id'],
                'file_md5': upload_obj['file_md5'],
                'format': upload_obj['format'],
                'ebook': f,
            }
            req = opener.open(
                "http://{0}/upload/{1}".format(host, urllib.quote_plus(session_key)), params
            )
            return req.read()

    except (HTTPError, URLError), e:
        raise SpinachError(str(e))
    except IOError, e:
        pass


def metadata_extract(calibre_ebook_meta_bin, filepath):
    extracted = subprocess.check_output(
        [calibre_ebook_meta_bin, filepath], stderr=subprocess.STDOUT
    )

    if extracted.find('EPubException') > 0:
        raise CorruptEbookError(extracted)

    # initialize all the metadata we attempt to extract
    meta = {}
    for prop in ('title', 'author', 'firstname', 'lastname', 'publisher',
                 'published', 'tags', 'isbn', 'asin', 'uri', 'ogre_id', 'dedrm'):
        meta[prop] = None

    for line in extracted.splitlines():
        # extract the simple metadata
        for prop in ('title', 'publisher', 'published'):
            if line.lower().startswith(prop):
                meta[prop] = line[line.find(':')+1:].strip()
                continue

        if 'Tags' in line:
            meta['tags'] = line[line.find(':')+1:].strip()

            # extract the DeDRM flag
            #if 'DeDRM' in meta['tags']:
            #    import pdb;pdb.set_trace()
            #    tags = meta['tags'].split(', ')
            #    for j in reversed(xrange(len(tags))):
            #        if 'DeDRM' in tags[j]:
            #            meta['dedrm'] = tags[j][6:]
            #            del(tags[j])
            #    meta['tags'] = ', '.join(tags)
            continue

        if 'Author' in line:
            meta['author'] = line[line.find(':')+1:].strip()
            bracketpos = meta['author'].find('[')
            if(bracketpos > -1):
                commapos = meta['author'].find(',', bracketpos)
                meta['lastname'] = meta['author'][bracketpos+1:commapos]
                meta['firstname'] = meta['author'][commapos+1:-1].strip()
                meta['author'] = meta['author'][0:bracketpos].strip()
            continue

        if 'Identifiers' in line:
            identifiers = line[line.find(':')+1:].strip()
            for ident in identifiers.split(','):
                if ident.startswith('isbn'):
                    meta['isbn'] = ident[5:].strip()
                if ident.startswith('mobi-asin'):
                    meta['asin'] = ident[8:].strip()
                if ident.startswith('uri'):
                    meta['uri'] = ident[3:].strip()
                if ident.startswith('epubbud'):
                    meta['epubbud'] = ident[7:].strip()
                if ident.startswith('ogre_id'):
                    meta['ogre_id'] = ident[7:].strip()
            continue

    return meta


def add_ogre_id_to_ebook(calibre_ebook_meta_bin, file_md5, filepath, format, ogre_id, host, session_key):
    with make_temp_directory() as temp_dir:
        # copy the ebook to a temp file
        tmp_name = '{}.{}'.format(os.path.join(temp_dir, id_generator()), format)
        shutil.copy(filepath, tmp_name)

        try:
            # write new tags
            subprocess.check_output(
                [calibre_ebook_meta_bin, tmp_name, '--identifier', 'ogre_id:{}'.format(ogre_id)],
                stderr=subprocess.STDOUT
            )

            # calculate new MD5 after updating metadata
            new_md5 = compute_md5(tmp_name)[0]

            # ping ogreserver with the book's new hash
            req = urllib2.Request(
                url='http://{}/confirm/{}'.format(host, urllib.quote_plus(session_key))
            )
            req.add_data(urllib.urlencode({
                'file_md5': file_md5,
                'new_md5': new_md5
            }))
            resp = urllib2.urlopen(req)
            data = resp.read()

            if data == 'ok':
                # move file back into place
                shutil.copy(tmp_name, filepath)
            else:
                raise FailedConfirmError("Server said 'no'")

        except subprocess.CalledProcessError as e:
            raise FailedWritingMetaDataError(str(e))

        except (HTTPError, URLError) as e:
            raise FailedConfirmError(str(e))
