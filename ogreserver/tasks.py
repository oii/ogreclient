import os
import subprocess

from ogreserver import app, celery

from ogreserver.models.user import User
from ogreserver.models.datastore import DataStore, S3DatastoreError
from ogreserver.models.reputation import Reputation
from ogreserver.models.log import Log


@celery.task(name="ogreserver.store_ebook")
def store_ebook(user_id, sdb_key, title, filemd5, fmt):
    """
    Store an ebook in the datastore
    """
    try:
        filepath = "%s/%s.%s" % (app.config['UPLOADED_EBOOKS_DEST'], filemd5, fmt)
        filename = DataStore.generate_filename(title, filemd5, fmt)

        # extract ebook meta
        meta = subprocess.Popen(['ebook-meta', filepath], 
                                stdout=subprocess.PIPE).communicate()[0]

        user = User.query.get(user_id)

        print "store_ebook: %s %s %s" % (filename, filemd5, user)

        # store the file into S3
        DataStore.store_ebook(sdb_key, filemd5, filename, filepath)

        # flag the book as having DRM removed
        if "Tags                : DeDRM" in meta:
            DataStore.set_dedrm_flag(sdb_key)

        # stats log the upload
        Log.create(user.id, "STORED", 1)

        # handle badge and reputation changes
        r = Reputation(user)
        r.earn_badges()

        # always delete local file
        os.remove(filepath)

    except S3DatastoreError:
        # TODO log this shit
        pass


@celery.task(name="ogreserver.convert_ebook")
def convert_ebook(sdbkey, source_filepath, dest_fmt):
    """
    Convert an ebook to another format, and push to datastore
    """
    pass
    #source_filepath = "%s/%s.%s" % (app.config['UPLOADED_EBOOKS_DEST'], filemd5, fmt)

    #for convert_fmt in app.config['EBOOK_FORMATS']:
    #    if fmt == convert_fmt:
    #        continue

    #    dest_filepath = "%s/%s.%s" % (app.config['UPLOADED_EBOOKS_DEST'], filemd5, fmt)

    #    meta = subprocess.Popen(['ebook-convert', source_filepath, ], 
    #                            stdout=subprocess.PIPE).communicate()[0]

    #if store == True:
    #    if user_id == None:
    #        raise Exception("user_id must be supplied to convert_ebook when store=True")

    #    store_ebook.delay(user_id, sdbkey, filemd5, fmt)


# TODO nightly which recalculates book ratings: 
#      10% of entire database per night (LOG the total and time spent)

# TODO nightly which check books are stored on S3 and updates SDB 

