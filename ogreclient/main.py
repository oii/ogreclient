from __future__ import absolute_import
from __future__ import unicode_literals

import os

from ogreclient import exceptions
from ogreclient.core.dedrm import clean_all_drm
from ogreclient.core.scan import scan_for_ebooks
from ogreclient.core.upload import query_for_uploads, upload_ebooks
from ogreclient.utils.connection import OgreConnection
from ogreclient.utils.printer import CliPrinter


prntr = CliPrinter.get_printer()


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

    try:
        # 2) remove DRM
        decrypt_errord = clean_all_drm(config, ebooks_by_authortitle, ebooks_by_filehash)

    except exceptions.AbortSyncDueToBadKey:
        if 'has_restarted_once' in config:
            prntr.info('Invalid Kindle error. Continuing without Kindle decryption')
        else:
            config['has_restarted_once'] = True

            # delete existing key and restart the sync
            os.remove(os.path.join(config['config_dir'], 'kindlekey.k4i'))

            prntr.info('Invalid Kindle key detected. Restarting sync.', bold=True)
            sync(config)
            return

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
    all_errord = [err for err in scan_errord+decrypt_errord if isinstance(err, exceptions.OgreException)]

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
        if isinstance(e, exceptions.CorruptEbookError):
            if 'corrupt' not in errors.keys():
                errors['corrupt'] = 1
            else:
                errors['corrupt'] += 1
        elif isinstance(e, exceptions.DuplicateEbookBaseError):
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

    except exceptions.RequestError as e:
        raise exceptions.SyncError(inner_excp=e)

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

        except (exceptions.FailedWritingMetaDataError, exceptions.FailedConfirmError) as e:
            prntr.error('Failed saving OGRE_ID in {}'.format(ebook_obj.shortpath), excp=e)
            failed += 1

    if config['verbose'] and success > 0:
        prntr.info('Updated {} ebooks'.format(success), success=True)
    if failed > 0:
        prntr.error('Failed updating {} ebooks'.format(failed))


def send_logs(connection, errord_list):
    try:
        # concat all stored log data
        log_data = '\n'.join(prntr.logs).encode('utf-8')

        # post all logs to ogreserver
        data = connection.request('post-logs', data={'raw_logs':log_data})

        if data['result'] != 'ok':
            raise exceptions.FailedDebugLogsError('Failed storing the logs, please report this.')
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

    except exceptions.RequestError as e:
        raise exceptions.FailedDebugLogsError(inner_excp=e)
