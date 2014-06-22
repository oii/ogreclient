from __future__ import absolute_import

import os
import json
import subprocess

from .extensions.celery import celery
from .extensions.database import get_db

from .models.user import User
from .models.datastore import DataStore, S3DatastoreError
from .models.reputation import Reputation
from .models.log import Log


@celery.task()
def store_ebook(user_id, ebook_id, file_md5, fmt):
    """
    Store an ebook in the datastore
    """
    # import the Flask app and spoof a context
    from .runflask import app
    with app.test_request_context():
        filepath = None

        # initialise the DB connection in our fake app context
        get_db(app)

        try:
            # create the datastore & generate a nice filename
            ds = DataStore(app.config, app.logger)
            filename = ds.generate_filename(file_md5)

            # storage path
            filepath = os.path.join(app.config['UPLOADED_EBOOKS_DEST'], '{}.{}'.format(file_md5, fmt))

            user = User.query.get(user_id)

            # store the file into S3
            if ds.store_ebook(ebook_id, file_md5, filename, filepath, fmt):
                # stats log the upload
                Log.create(user.id, 'STORED', 1)

                # handle badge and reputation changes
                r = Reputation(user)
                r.earn_badges()
            else:
                app.logger.info('{} exists on S3'.format(filename))

        except S3DatastoreError as e:
            app.logger.error('Failed uploading {} with {}'.format(filename, e))

        finally:
            # always delete local file
            if filepath is not None and os.path.exists(filepath):
                os.remove(filepath)


@celery.task()
def convert_ebook(sdbkey, source_filepath, dest_fmt):
    """
    Convert an ebook to another format, and push to datastore
    """
    pass
    #source_filepath = "%s/%s.%s" % (app.config['UPLOADED_EBOOKS_DEST'], file_md5, fmt)

    #for convert_fmt in app.config['EBOOK_FORMATS']:
    #    if fmt == convert_fmt:
    #        continue

    #    dest_filepath = "%s/%s.%s" % (app.config['UPLOADED_EBOOKS_DEST'], file_md5, fmt)

    #    meta = subprocess.Popen(['ebook-convert', source_filepath, ], 
    #                            stdout=subprocess.PIPE).communicate()[0]

    #if store == True:
    #    if user_id == None:
    #        raise Exception("user_id must be supplied to convert_ebook when store=True")

    #    store_ebook.delay(user_id, sdbkey, file_md5, fmt)


# TODO nightly which recalculates book ratings: 
#      10% of entire database per night (LOG the total and time spent)

# TODO nightly which check books are stored on S3 and updates SDB 

