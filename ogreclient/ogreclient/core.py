from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import division

import os
import shutil

from .ebook_obj import EbookObject
from .utils import OgreConnection, deserialize_defs, make_temp_directory, retry
from .printer import CliPrinter
from .providers import LibProvider, PathsProvider
from .dedrm import decrypt, DRM

from .exceptions import RequestError, NoEbooksError, DuplicateEbookBaseError, \
        ExactDuplicateEbookError, AuthortitleDuplicateEbookError, EbookIdDuplicateEbookError, \
        SyncError, UploadError, CorruptEbookError, FailedWritingMetaDataError, \
        FailedConfirmError, FailedDebugLogsError, MissingFromCacheError, OgreException, \
        FailedUploadsQueryError, FailedGettingDefinitionsError, DeDrmMissingError, DecryptionFailed


prntr = CliPrinter.get_printer()


def get_definitions(connection):
    try:
        # retrieve the ebook format definitions
        data = connection.request('definitions')

        # convert list of lists result into OrderedDict
        return deserialize_defs(data)

    except RequestError as e:
        raise FailedGettingDefinitionsError(inner_excp=e)


def sync(config):
    # authenticate user and generate session API key
    connection = OgreConnection(config)
    connection.login(config['username'], config['password'])

    # let the user know something is happening
    prntr.info('Scanning for ebooks..', nonl=True, bold=True)

    # 1) find ebooks in config['ebook_home'] on local machine
    ebooks_by_authortitle, ebooks_by_filehash, scan_errord, skipped = scan_for_ebooks(config)

    if scan_errord:
        prntr.info('Errors occurred during scan:')
        for e in scan_errord:
            prntr.error(e.ebook_obj.path, excp=e)

    # 2) remove DRM
    decrypt_errord = clean_all_drm(config, ebooks_by_authortitle, ebooks_by_filehash)

    if decrypt_errord:
        prntr.info('Errors occurred during decryption:')
        for e in decrypt_errord:
            # display an error message
            prntr.error(e.ebook_obj.path, excp=e)
            # remove the book from the sync data
            del(ebooks_by_filehash[e.ebook_obj.file_hash])
            del(ebooks_by_authortitle[e.ebook_obj.authortitle])

    # display a friendly count of books found/skipped
    prntr.info('Found {} ebooks total{}'.format(
        len(ebooks_by_authortitle) + skipped,
        ', {} skipped'.format(skipped) if skipped > 0 else ''
    ), bold=True)

    # 3) send dict of ebooks / md5s to ogreserver
    response = sync_with_server(config, connection, ebooks_by_authortitle)

    prntr.info('Come on sucker, lick my battery', bold=True)

    # 4) set ogre_id in metadata of each sync'd ebook
    update_local_metadata(config, connection, ebooks_by_filehash, response['to_update'])

    # 5) query the set of books to upload
    ebooks_to_upload = query_for_uploads(config, connection)

    # 6) upload the ebooks requested by ogreserver
    uploaded_count = upload_ebooks(config, connection, ebooks_by_filehash, ebooks_to_upload)

    # 7) display/send errors
    all_errord = [err for err in scan_errord+decrypt_errord if isinstance(err, OgreException)]

    if all_errord:
        if not config['debug']:
            prntr.error('Finished with errors. Re-run with --debug to send logs to OGRE')
        else:
            # send a log of all events, and upload bad books
            send_logs(connection, all_errord)

    return uploaded_count


def scan_and_show_stats(config):
    ebooks_by_authortitle, ebooks_by_filehash, errord_list, _ = scan_for_ebooks(config)

    counts = {}
    errors = {}

    # iterate authortitle:EbookObject pairs
    for key, e in ebooks_by_authortitle.iteritems():
        if e.format not in counts.keys():
            counts[e.format] = 1
        else:
            counts[e.format] += 1

    # iterate list of exceptions
    for e in errord_list:
        if isinstance(e, CorruptEbookError):
            if 'corrupt' not in errors.keys():
                errors['corrupt'] = 1
            else:
                errors['corrupt'] += 1
        elif isinstance(e, DuplicateEbookBaseError):
            if 'duplicate' not in errors.keys():
                errors['duplicate'] = 1
            else:
                errors['duplicate'] += 1

    # add header to output table
    output = [('format', 'count')]
    output += [(k,v) for k,v in counts.iteritems()]
    # add a separator row and the error counts
    output.append(('-', '-'))
    output += [(k,v) for k,v in errors.iteritems()]

    # print table
    prntr.info(output, tabular=True, notime=True)


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
        raise NoEbooksError

    prntr.info('Scanning ebook meta data..')
    ebooks_by_authortitle = {}
    ebooks_by_filehash = {}
    errord_list = []

    for item in ebooks:
        try:
            # optionally skip the cache
            if config['skip_cache'] is True:
                raise MissingFromCacheError

            # get ebook from the cache
            ebook_obj = config['ebook_cache'].get_ebook(path=item[0])

        except MissingFromCacheError:
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

            except CorruptEbookError as e:
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
                ExactDuplicateEbookError(ebook_obj, ebooks_by_authortitle[ebook_obj.authortitle].path)
            )
        elif ebook_obj.authortitle in ebooks_by_authortitle.keys() and ebooks_by_authortitle[ebook_obj.authortitle].format == ebook_obj.format:
            # warn user on error stack
            errord_list.append(
                AuthortitleDuplicateEbookError(ebook_obj, ebooks_by_authortitle[ebook_obj.authortitle].path)
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

        except EbookIdDuplicateEbookError as e:
            # handle duplicate books with same ebook_id in metadata
            errord_list.append(e)

        i += 1
        prntr.progressf(num_blocks=i, total_size=len(ebooks))

    if len(ebooks_by_authortitle) == 0:
        return {}, {}, errord_list, skipped

    return ebooks_by_authortitle, ebooks_by_filehash, errord_list, skipped


def clean_all_drm(config, ebooks_by_authortitle, ebooks_by_filehash):
    errord_list = []

    i = 0
    cleaned = 0

    prntr.info('Ebook directory is {}'.format(config['ebook_home']))
    prntr.info('Decrypting DRM..')

    for authortitle, ebook_obj in ebooks_by_authortitle.iteritems():
        # skip if book already DRM free or marked skip
        if ebook_obj.drmfree is True or ebook_obj.skip is True:
            continue

        # only attempt decrypt on ebooks which are defined as a valid format
        if config['definitions'][ebook_obj.format].is_valid_format is False:
            continue

        try:
            # remove DRM from ebook
            new_ebook_obj = remove_drm_from_ebook(config, ebook_obj)

            if new_ebook_obj is not None:
                # update the sync data with the decrypted ebook
                ebooks_by_authortitle[authortitle] = new_ebook_obj
                del(ebooks_by_filehash[ebook_obj.file_hash])
                ebooks_by_filehash[new_ebook_obj.file_hash] = new_ebook_obj
                cleaned += 1

        # record books which failed decryption
        except DeDrmMissingError as e:
            errord_list.append(DeDrmMissingError(ebook_obj))
            continue
        except (CorruptEbookError, DecryptionFailed) as e:
            errord_list.append(e)
            continue

        if config['verbose'] is False:
            i += 1
            prntr.progressf(num_blocks=i, total_size=len(ebooks_by_authortitle))

    if config['verbose'] and cleaned > 0:
        prntr.info('Cleaned DRM from {} ebooks'.format(cleaned), success=True)

    return errord_list


def remove_drm_from_ebook(config, ebook_obj):
    decrypted_ebook_obj = None

    # extract suffix
    _, suffix = os.path.splitext(os.path.basename(ebook_obj.path))

    try:
        # decrypt into a temp path
        with make_temp_directory() as ebook_output_path:
            state, decrypted_filepath = decrypt(
                ebook_obj.path, suffix, config['config_dir'], output_dir=ebook_output_path
            )

            if state == DRM.none:
                # update cache to mark book as drmfree
                config['ebook_cache'].update_ebook_property(ebook_obj.path, drmfree=True)

            elif state == DRM.decrypted:
                # create new ebook_obj for decrypted ebook
                decrypted_ebook_obj = EbookObject(
                    config=config,
                    filepath=decrypted_filepath,
                    source=ebook_obj.meta['source']
                )

                # add the OGRE DeDRM tag to the decrypted ebook
                decrypted_ebook_obj.add_dedrm_tag()
                decrypted_ebook_obj.compute_md5()

                # move decrypted book into ebook library
                decrypted_ebook_obj.path = os.path.join(
                    config['ebook_home'], os.path.basename(decrypted_filepath)
                )
                shutil.move(decrypted_filepath, decrypted_ebook_obj.path)

                if config['verbose']:
                    prntr.info('Decrypted ebook {} moved to {}'.format(
                        os.path.basename(ebook_obj.path),
                        decrypted_ebook_obj.shortpath
                    ), success=True)

                # add decrypted book to cache
                config['ebook_cache'].store_ebook(decrypted_ebook_obj)

                # update existing DRM-scuppered book as skip=True in cache
                config['ebook_cache'].update_ebook_property(ebook_obj.path, skip=True)

            else:
                # mark book as having DRM
                config['ebook_cache'].update_ebook_property(ebook_obj.path, drmfree=False)

                if state == DRM.wrong_key:
                    raise DecryptionFailed(ebook_obj, 'Incorrect key found for ebook')
                elif state == DRM.corrupt:
                    raise DecryptionFailed(ebook_obj, 'Corrupt ebook found')
                else:
                    raise DecryptionFailed(ebook_obj, 'Unknown error in decryption ({})'.format(state))

    except UnicodeDecodeError as e:
        raise CorruptEbookError(ebook_obj, 'Unicode filename problem', inner_excp=e)

    return decrypted_ebook_obj


def sync_with_server(config, connection, ebooks_by_authortitle):
    # serialize ebooks to dictionary for sending to ogreserver
    ebooks_for_sync = {}
    for authortitle, ebook_obj in ebooks_by_authortitle.iteritems():
        # only send format is defined as is_valid_format
        if config['definitions'][ebook_obj.format][0] is True:
            ebooks_for_sync[authortitle] = ebook_obj.serialize()

    try:
        # post json dict of ebook data
        data = connection.request('post', data=ebooks_for_sync)

    except RequestError as e:
        raise SyncError(inner_excp=e)

    # display server messages
    for msg in data['messages']:
        if len(msg) == 2:
            prntr.info('{} {}'.format(msg[0], msg[1]))
        else:
            prntr.info(msg)

    for msg in data['errors']:
        prntr.error(msg)

    return data


def update_local_metadata(config, connection, ebooks_by_filehash, ebooks_to_update):
    success, failed = 0, 0

    # update any books with ogre_id supplied from ogreserver
    for file_hash, item in ebooks_to_update.iteritems():
        ebook_obj = ebooks_by_filehash[file_hash]

        try:
            # update the metadata on the ebook, and communicate that to ogreserver
            new_file_hash = ebook_obj.add_ogre_id_tag(item['ebook_id'], connection)

            # update the global dict with the new file_hash
            del(ebooks_by_filehash[file_hash])
            ebooks_by_filehash[new_file_hash] = ebook_obj

            success += 1
            if config['verbose']:
                prntr.info('Wrote OGRE_ID to {}'.format(ebook_obj.shortpath))

            # write to ogreclient cache
            config['ebook_cache'].update_ebook_property(
                ebook_obj.path,
                file_hash=new_file_hash,
                ebook_id=item['ebook_id']
            )

        except (FailedWritingMetaDataError, FailedConfirmError) as e:
            prntr.error('Failed saving OGRE_ID in {}'.format(ebook_obj.shortpath), excp=e)
            failed += 1

    if config['verbose'] and success > 0:
        prntr.info('Updated {} ebooks'.format(success), success=True)
    if failed > 0:
        prntr.error('Failed updating {} ebooks'.format(failed))


def query_for_uploads(config, connection):
    try:
        # query ogreserver for books to upload
        data = connection.request('to-upload')
        return data['result']

    except RequestError as e:
        raise FailedUploadsQueryError(inner_excp=e)


def upload_ebooks(config, connection, ebooks_by_filehash, ebooks_to_upload):
    if len(ebooks_to_upload) == 0:
        return 0

    @retry(times=3)
    def upload_single_book(connection, ebook_obj):
        try:
            connection.upload(
                'upload',
                ebook_obj,
                data={
                    'ebook_id': ebook_obj.ebook_id,
                    'file_hash': ebook_obj.file_hash,
                    'format': ebook_obj.format,
                },
            )

        except RequestError as e:
            raise UploadError(ebook_obj, inner_excp=e)
        except IOError as e:
            raise UploadError(ebook_obj, inner_excp=e)

    # grammatically correct messages are nice
    plural = 's' if len(ebooks_to_upload) > 1 else ''

    prntr.info('Uploading {} file{}. Go make a brew.'.format(len(ebooks_to_upload), plural), bold=True)

    success, i = 0, 0
    failed_uploads = []

    # upload each requested by the server
    for file_hash in ebooks_to_upload:
        ebook_obj = ebooks_by_filehash[file_hash]

        # TODO progress bar the uploads
        # https://gitlab.com/sigmavirus24/toolbelt/blob/master/examples/monitor/progress_bar.py

        # failed uploads are retried three times; total fail will raise the last exception
        try:
            upload_single_book(connection, ebook_obj)

        except UploadError as e:
            # record failures for later
            failed_uploads.append(e)
        else:
            if config['verbose'] is True:
                prntr.info('Uploaded {}'.format(ebook_obj.shortpath))
            success += 1

        if config['verbose'] is False:
            i += 1
            prntr.progressf(num_blocks=i, total_size=len(ebooks_to_upload))

    # only print completion message after all retries
    if success > 0:
        prntr.info('Completed {} uploads'.format(success), success=True)

    if len(failed_uploads) > 0:
        prntr.error('Failed uploading {} ebooks:'.format(len(failed_uploads)))
        for e in failed_uploads:
            prntr.error(
                '{}'.format(
                    ebooks_by_filehash[e.ebook_obj.file_hash].path
                ), excp=e.inner_excp
            )
        prntr.info('Please run another sync', success=True)

    return success


def send_logs(connection, errord_list):
    try:
        # concat all stored log data
        log_data = '\n'.join(prntr.logs).encode('utf-8')

        # post all logs to ogreserver
        data = connection.request('post-logs', data={'raw_logs':log_data})

        if data['result'] != 'ok':
            raise FailedDebugLogsError('Failed storing the logs, please report this.')
        else:
            prntr.info('Uploaded logs to OGRE')

        # upload all books which failed
        if errord_list:
            prntr.info('Uploaded failed books to OGRE for debug..')
            i = 0

            for e in errord_list:
                connection.upload(
                    'upload-errord',
                    e.ebook_obj,
                    data={
                        'filename': os.path.basename(e.ebook_obj.path.encode('utf-8'))
                    },
                )

                i += 1
                prntr.progressf(num_blocks=i, total_size=len(errord_list))

    except RequestError as e:
        raise FailedDebugLogsError(inner_excp=e)
