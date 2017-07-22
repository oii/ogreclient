from __future__ import absolute_import
from __future__ import unicode_literals

from ogreclient import exceptions
from ogreclient.utils import retry
from ogreclient.utils.printer import CliPrinter


prntr = CliPrinter.get_printer()


def query_for_uploads(config, connection):
    try:
        # query ogreserver for books to upload
        data = connection.request('to-upload')
        return data['result']

    except exceptions.RequestError as e:
        raise exceptions.FailedUploadsQueryError(inner_excp=e)


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

        except exceptions.RequestError as e:
            raise exceptions.UploadError(ebook_obj, inner_excp=e)
        except IOError as e:
            raise exceptions.UploadError(ebook_obj, inner_excp=e)

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

        except exceptions.UploadError as e:
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
