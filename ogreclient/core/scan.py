from __future__ import absolute_import
from __future__ import unicode_literals

import os

from ogreclient import exceptions
from ogreclient.core.ebook_obj import EbookObject
from ogreclient.providers import LibProvider, PathsProvider
from ogreclient.utils.printer import CliPrinter


prntr = CliPrinter.get_printer()


def scan_for_ebooks(config):
    ebooks = []

    def _process_filename(filename, provider_name):
        fn, ext = os.path.splitext(filename)
        # check file not hidden, is in list of known file suffixes
        if fn[1:1] != '.' and ext[1:] in config['definitions'].keys():
            ebooks.append(
                (os.path.join(root, filename), ext[1:], provider_name)
            )

    for provider in config['providers'].itervalues():
        # a LibProvider contains a single directory containing ebooks
        if isinstance(provider, LibProvider):
            if config['debug']:
                prntr.info('Scanning {} in {}'.format(provider.friendly, provider.libpath))

            for root, _, files in os.walk(provider.libpath):
                for filename in files:
                    _process_filename(filename, provider.friendly)

        # a PathsProvider contains a list of direct ebook paths
        elif isinstance(provider, PathsProvider):
            if config['debug']:
                prntr.info('Scanning {}'.format(provider.friendly))

            for path in provider.paths:
                _process_filename(filename, provider.friendly)

    i = 0
    skipped = 0
    prntr.info('Discovered {} files'.format(len(ebooks)), bold=True)
    if len(ebooks) == 0:
        raise exceptions.NoEbooksError

    prntr.info('Scanning ebook meta data..')
    ebooks_by_authortitle = {}
    ebooks_by_filehash = {}
    errord_list = []

    for item in ebooks:
        if config['verbose']:
            prntr.info('Meta data scanning {}'.format(item[0]))

        try:
            # optionally skip the cache
            if config['skip_cache'] is True:
                raise exceptions.MissingFromCacheError

            # get ebook from the cache
            ebook_obj = config['ebook_cache'].get_ebook(path=item[0])

        except exceptions.MissingFromCacheError:
            # init the EbookObject
            ebook_obj = EbookObject(
                config=config,
                filepath=item[0],
                fmt=item[1],
                source=item[2],
            )
            # calculate MD5 of ebook
            ebook_obj.compute_md5()

            try:
                # extract ebook metadata and build key; books are stored in a dict
                # with 'authortitle' as the key in a naive attempt at de-duplication
                ebook_obj.get_metadata()

            except exceptions.CorruptEbookError as e:
                # record books which failed during scan
                errord_list.append(e)

                # add book to the cache as a skip
                ebook_obj.skip = True
                config['ebook_cache'].store_ebook(ebook_obj)

        # skip previously scanned books which are marked skip (DRM'd or duplicates)
        if ebook_obj.skip:
            skipped += 1
            i += 1
            prntr.progressf(num_blocks=i, total_size=len(ebooks))
            continue

        # check for identical filehash (exact duplicate) or duplicated authortitle/format
        if ebook_obj.file_hash in ebooks_by_filehash.keys():
            # warn user on error stack
            errord_list.append(
                exceptions.ExactDuplicateEbookError(
                    ebook_obj, ebooks_by_authortitle[ebook_obj.authortitle].path
                )
            )
        elif ebook_obj.authortitle in ebooks_by_authortitle.keys() and ebooks_by_authortitle[ebook_obj.authortitle].format == ebook_obj.format:
            # warn user on error stack
            errord_list.append(
                exceptions.AuthortitleDuplicateEbookError(
                    ebook_obj, ebooks_by_authortitle[ebook_obj.authortitle].path
                )
            )
        else:
            # new ebook, or different format of duplicate ebook found
            write = False

            if ebook_obj.authortitle in ebooks_by_authortitle.keys():
                # compare the rank of the format already found against this one
                existing_rank = config['definitions'].keys().index(ebooks_by_authortitle[ebook_obj.authortitle].format)
                new_rank = config['definitions'].keys().index(ebook_obj.format)

                # lower is better
                if new_rank < existing_rank:
                    write = True
            else:
                # new book found
                write = True

            if write:
                # output dictionary for sending to ogreserver
                ebooks_by_authortitle[ebook_obj.authortitle] = ebook_obj

                # track all unique file hashes found
                ebooks_by_filehash[ebook_obj.file_hash] = ebook_obj
            else:
                ebook_obj.skip = True

        try:
            # add book to the cache
            config['ebook_cache'].store_ebook(ebook_obj)

        except exceptions.EbookIdDuplicateEbookError as e:
            # handle duplicate books with same ebook_id in metadata
            errord_list.append(e)

        i += 1
        if config['verbose'] is False:
            prntr.progressf(num_blocks=i, total_size=len(ebooks))

    if len(ebooks_by_authortitle) == 0:
        return {}, {}, errord_list, skipped

    return ebooks_by_authortitle, ebooks_by_filehash, errord_list, skipped
