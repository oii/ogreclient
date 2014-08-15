from __future__ import absolute_import

import hashlib
import re

import rethinkdb as r

import boto
from boto.exception import S3ResponseError

from whoosh.query import Every
from whoosh.qparser import MultifieldParser, OrGroup

from .user import User
from .utils import connect_s3

from ..exceptions import OgreException, BadMetaDataError, ExactDuplicateError


class DataStore():
    def __init__(self, config, logger, whoosh=None):
        self.config = config
        self.logger = logger
        self.whoosh = whoosh

    def update_library(self, ebooks, user):
        """
        The core library synchronisation method.
        A dict containing ebook metadata and file hashes is sent by each client
        and synchronised against the contents of the OGRE database.
        """
        output = {}

        conn = r.connect("localhost", 28015, db=self.config['RETHINKDB_DATABASE'])

        for authortitle, incoming in ebooks.items():
            try:
                # build output to return to client
                output[incoming['file_hash']] = {'new': False, 'update': False, 'dupe': False}

                skip_existing = False
                if 'ebook_id' in incoming and incoming['ebook_id'] is not None:
                    skip_existing = True
                else:
                    # tell client to set ogre_id on this ebook
                    output[incoming['file_hash']]['update'] = True

                # first check if this exact file has been uploaded before
                # query formats table by key, joining to versions to get ebook pk
                existing = list(
                    r.table('formats').filter(
                        {'file_hash': incoming['file_hash']}
                    ).eq_join(
                        'version_id', r.table('versions')
                    ).zip().run(conn)
                )

                # skip existing books
                if skip_existing is True or len(existing) > 0:
                    output[incoming['file_hash']]['ebook_id'] = existing[0]['ebook_id']
                    output[incoming['file_hash']]['dupe'] = True

                    raise ExactDuplicateError(
                        'Ignoring exact duplicate {} {}'.format(
                            existing[0]['ebook_id'],
                            authortitle.encode('UTF-8'),
                        )
                    )

                try:
                    # derive author and title from the key
                    author, title = authortitle.split(u'\u0007')
                    firstname, lastname = author.split(u'\u0006')
                except Exception as e:
                    raise BadMetaDataError(
                        'Bad meta data on {}'.format(incoming['file_hash']), e
                    )

                # check for this book by meta data in the library
                ebook_id = DataStore.build_ebook_key(lastname, firstname, title)
                existing = r.table('ebooks').get(ebook_id).run(conn)

                if existing is None:
                    # create this as a new book
                    new_book = {
                        'ebook_id': ebook_id,
                        'title': title,
                        'firstname': firstname,
                        'lastname': lastname,
                        'rating': None,
                        'comments': [],
                        'publisher': incoming['publisher'] if 'publisher' in incoming else None,
                        'publish_date': incoming['published'] if 'published' in incoming else None,
                        'meta': {
                            'isbn': incoming['isbn'] if 'isbn' in incoming else None,
                            'asin': incoming['asin'] if 'asin' in incoming else None,
                            'uri': incoming['uri'] if 'uri' in incoming else None,
                            'raw_tags': incoming['tags'] if 'tags' in incoming else None,
                        },
                    }
                    r.table('ebooks').insert(new_book).run(conn)

                    # add the first version
                    new_version = {
                        'ebook_id': ebook_id,
                        'user': user.username,
                        'size': incoming['size'],
                        'popularity': 1,
                        'quality': 0,
                        'original_format': incoming['format'],
                    }
                    ret = r.table('versions').insert(new_version).run(conn)

                    new_format = {
                        'file_hash': incoming['file_hash'],
                        'version_id': ret['generated_keys'][0],
                        'format': incoming['format'],
                        'uploaded': False,
                        'source_patched': False,
                    }
                    r.table('formats').insert(new_format).run(conn)

                    # mark book as new
                    output[incoming['file_hash']]['ebook_id'] = ebook_id
                    output[incoming['file_hash']]['new'] = True

                    # update the whoosh text search interface
                    self.index_for_search(new_book)

                else:
                    # parse the ebook data
                    other_versions = r.table('versions').filter(
                        {'ebook_id': ebook_id, 'user': user.username}
                    ).count().run(conn)

                    if other_versions > 0:
                        msg = "Rejecting new version of {} from {}".format(
                            authortitle.decode('UTF-8'), user.username
                        )
                        self.logger.info(msg)
                        continue

                    new_version = {
                        'ebook_id': ebook_id,
                        'user': user.username,
                        'size': incoming['size'],
                        'popularity': 1,
                        'quality': 0,
                        'original_format': incoming['format'],
                    }
                    ret = r.table('versions').insert(new_version).run(conn)

                    new_format = {
                        'file_hash': incoming['file_hash'],
                        'ebook_id': ebook_id,
                        'version_id': ret['generated_keys'][0],
                        'format': incoming['format'],
                        'uploaded': False,
                    }
                    r.table('formats').insert(new_format).run(conn)

                    # mark with ebook_id and return
                    output[incoming['file_hash']]['ebook_id'] = ebook_id

                    # TODO version popularity determines which formats appear on ebook base top-level
                    # popularity += 1 for download
                    # popularity += 1 for new owner
                    # use quality as co-efficient when calculating most popular
                    # see: versions_rank_algorithm()

            except OgreException as e:
                # TODO log this and report back to client
                self.logger.info(e)
            except Exception as e:
                self.logger.error(e, exc_info=True)

        return output


    def index_for_search(self, book_data):
        if self.whoosh is None:
            return

        author = " ".join((book_data['firstname'], book_data['lastname']))
        title = book_data['title']

        # add info about this book to the search index
        writer = self.whoosh.writer()
        try:
            writer.add_document(ebook_id=unicode(book_data['ebook_id']), author=author, title=title)
            writer.commit()
        except Exception as e:
            self.logger.error(e)


    def search(self, searchstr=None, page=1):
        """
        Search for books using whoosh, or return first page from all
        """
        if self.whoosh is None:
            return

        output = []

        if searchstr is None:
            # default to list all authors
            query = Every('author')
        else:
            # create a search by author and then title
            qp = MultifieldParser(['author', 'title'], self.whoosh.schema, group=OrGroup)
            query = qp.parse(searchstr)

        # start a paginated search
        with self.whoosh.searcher() as s:
            results = s.search_page(query, page, pagelen=20)
            for res in results:
                output.append(res.fields())

        return output


    def get_rating(self, ebook_id):
        """
        Get the user rating for this book
        """
        conn = r.connect("localhost", 28015, db=self.config['RETHINKDB_DATABASE'])
        return r.table('ebooks').get(ebook_id)['rating'].run(conn)

    def get_comments(self, ebook_id):
        """
        Get the list of comments on this book
        """
        conn = r.connect("localhost", 28015, db=self.config['RETHINKDB_DATABASE'])
        return r.table('ebooks').get(ebook_id)['comments'].run(conn)

    @staticmethod
    def build_ebook_key(lastname, firstname, title):
        """
        Generate a key for this ebook from the author and title
        This is used as the ebook's key in the DB - referred to as ebook_id in code
        """
        return hashlib.md5(
            ("~".join((lastname, firstname, title))).encode('UTF-8')
        ).hexdigest()

    @staticmethod
    def versions_rank_algorithm(version):
        """
        Generate a score for this version of an ebook

        The quality % score and the popularity score are ratioed together 70:30
        Since popularity is a scalar and can grow indefinitely it's divided
        by our num of total system users
        """
        total_users = User.get_total_users()
        return (version['quality'] * 0.7) + ((float(version['popularity']) / total_users) * 100 * 0.3)

    def get_ebook_url(self, ebook_id, fmt=None, version_id=None):
        """
        Generate a download URL for the requested ebook

        If a version isn't requested the top-ranked one will be supplied.
        If a format isn't requested one will be served in the order defined in EBOOK_FORMATS
        """
        conn = r.connect("localhost", 28015, db=self.config['RETHINKDB_DATABASE'])

        if version_id is None:
            versions = list(r.table('versions').filter({'ebook_id': ebook_id}).eq_join(
                'version_id', r.table('formats'), index='version_id'
            ).zip().run(conn))

            if len(versions) > 1:
                # sort this book's versions by quality & popularity
                versions = sorted(versions,
                    key=lambda v: DataStore.versions_rank_algorithm(v),
                    reverse=True
                )

            if fmt is None:
                # select top-ranked version
                version = versions[0]
                # serve the OGRE preferred format
                for fmt in self.config['EBOOK_FORMATS']:
                    if fmt == version['format']:
                        file_hash = version['file_hash']
                        break
            else:
                # serve the requested format from best version possible
                for version in versions:
                    if fmt == version['format']:
                        file_hash = version['file_hash']
                        break
        else:
            # get the specific requested version
            version = r.table('versions').filter({'version_id': version_id}).eq_join(
                'version_id', r.table('formats'), index='version_id'
            ).zip().run(conn)

            if fmt is None:
                # serve the OGRE preferred format
                for fmt in self.config['EBOOK_FORMATS']:
                    if fmt == version['format']:
                        file_hash = version['version_id']
                        break
            else:
                # verify requested format is available on requested version
                if fmt != version['format']:
                    raise Exception("Requested format not available on requested version.")
                else:
                    file_hash = version['version_id']

        # generate the filename - which is the key on S3
        filename = self.generate_filename(file_hash)

        # create an expiring auto-authenticate url for S3
        s3 = connect_s3(self.config)
        return s3.generate_url(self.config['DOWNLOAD_LINK_EXPIRY'], 'GET',
            bucket=self.config['S3_BUCKET'],
            key=filename
        )

    def update_book_hash(self, current_file_hash, updated_file_hash):
        """
        Update a format's entry with a new PK
        This is called after the OGRE-ID meta data is written into an ebook on the client
        """
        if current_file_hash == updated_file_hash:
            return None

        conn = r.connect("localhost", 28015, db=self.config['RETHINKDB_DATABASE'])
        data = r.table('formats').get(current_file_hash).run(conn)
        if data is None:
            self.logger.error('Format {} does not exist'.format(current_file_hash))
            return False
        try:
            data['file_hash'] = updated_file_hash
            data['source_patched'] = True
            r.table('formats').insert(data).run(conn)
            r.table('formats').get(current_file_hash).delete().run(conn)
            self.logger.info('Updated {} to {} on {}'.format(
                current_file_hash, updated_file_hash, data['version_id'])
            )
        except Exception:
            self.logger.error(
                'Failed updating format {} on {}'.format(current_file_hash, data['version_id']),
                exc_info=True
            )
            return False
        return True

    def set_uploaded(self, file_hash, isit=True):
        """
        Mark an ebook as having been uploaded to S3
        """
        conn = r.connect("localhost", 28015, db=self.config['RETHINKDB_DATABASE'])
        r.table('formats').get(file_hash).update({'uploaded': isit}).run(conn)

    def set_dedrm_flag(self, file_hash):
        """
        Mark a book as having had DRM removed
        """
        conn = r.connect("localhost", 28015, db=self.config['RETHINKDB_DATABASE'])
        r.table('formats').get(file_hash).update({'dedrm': True}).run(conn)

    def store_ebook(self, ebook_id, file_hash, filename, filepath, fmt):
        """
        Store an ebook on S3
        """
        s3 = connect_s3(self.config)
        bucket = s3.get_bucket(self.config['S3_BUCKET'])

        # create a new storage key
        k = boto.s3.key.Key(bucket)
        k.key = filename

        # check if our file is already up on S3
        if k.exists() is True:
            k = bucket.get_key(filename)
            metadata = k._get_remote_metadata()
            if 'x-amz-meta-ogre-key' in metadata and metadata['x-amz-meta-ogre-key'] == ebook_id:
                # if already exists, abort and flag as uploaded
                self.set_uploaded(file_hash)
                return False

        # calculate uploaded file md5
        f = open(filepath, "rb")
        md5_tup = k.compute_md5(f)
        f.close()

        # error check uploaded file
        if file_hash != md5_tup[0]:
            # TODO logging
            raise S3DatastoreError("Upload failed checksum 1")
        else:
            try:
                # TODO time this and print
                # push file to S3
                k.set_contents_from_filename(filepath,
                    headers={'x-amz-meta-ogre-key': ebook_id},
                    md5=md5_tup,
                )
                self.logger.info('UPLOADED {}'.format(filename))

                # mark ebook as stored
                self.set_uploaded(file_hash)

            except S3ResponseError:
                # TODO log
                raise S3DatastoreError("Upload failed checksum 2")

        return True


    def generate_filename(self, file_hash, firstname=None, lastname=None, title=None, format=None):
        """
        Generate the filename for a book on its way to S3

        firstname, lastname, title & format are loaded if they are not supplied
        """
        if firstname is not None and type(firstname) is not unicode:
            raise UnicodeWarning('Firstname must be unicode')
        if title is not None and type(title) is not unicode:
            raise UnicodeWarning('Title must be unicode')
        if lastname is not None and type(lastname) is not unicode:
            raise UnicodeWarning('Lastname must be unicode')

        if firstname is None or lastname is None or title is None:
            conn = r.connect("localhost", 28015, db=self.config['RETHINKDB_DATABASE'])

            # load the author and title of this book
            ebook_data = list(
                r.table('formats').filter({'file_hash': file_hash}).eq_join(
                    'version_id', r.table('versions'), index='version_id'
                ).zip().eq_join(
                    'ebook_id', r.table('ebooks'), index='ebook_id'
                ).zip().pluck(
                    'firstname', 'lastname', 'title', 'format'
                ).run(conn)
            )[0]
            firstname = ebook_data['firstname']
            lastname = ebook_data['lastname']
            title = ebook_data['title']
            format = ebook_data['format']

        elif format is None:
            # load the file format for this book's hash
            conn = r.connect("localhost", 28015, db=self.config['RETHINKDB_DATABASE'])
            format = r.table('formats').get(file_hash).pluck('format').run(conn)['format']

        # transpose unicode for ASCII filenames
        from unidecode import unidecode
        firstname = unidecode(firstname)
        lastname = unidecode(lastname)
        title = unidecode(title)

        # remove apostrophes & strip whitespace
        if "'" in firstname:
            firstname = firstname.replace("'", '').strip()
        if "'" in lastname:
            lastname = lastname.replace("'", '').strip()
        if "'" in title:
            title = title.replace("'", '').strip()

        # only alphabet allowed in filename; replace all else with underscore
        authortitle = re.sub('[^a-zA-Z0-9~]', '_', '{}_{}~~{}'.format(
            firstname, lastname, title
        ))

        # replace multiple underscores with a single
        # replace double tilde between author & title with double underscore
        authortitle = re.sub('(~|_+)', '_', authortitle)

        return '{}.{}.{}'.format(authortitle, file_hash[0:8], format)


    def get_missing_books(self, username=None, hash_filter=None, verify_s3=False):
        """
        Query the DB for books marked as not uploaded

        The verify_s3 flag enables a further check to be run against S3 to ensure 
        the file is actually there
        """
        if username is None and hash_filter is None and verify_s3 is True:
            raise Exception("Can't verify entire library in one go.")

        conn = r.connect("localhost", 28015, db=self.config['RETHINKDB_DATABASE'])

        # query the formats table for missing ebooks
        query = r.table('formats').filter({'uploaded': False})

        # filter by list of md5 file hashes
        if hash_filter is not None:
            query = r.expr(hash_filter).do(
                lambda hash_filter: query.filter(
                    lambda d: hash_filter.contains(d['file_hash'])
                )
            )

        # join up to the versions table
        query = query.eq_join('version_id', r.table('versions'), index='version_id').zip()

        # filter by username
        if username is not None:
            query = query.filter({'user': username})

        cursor = query.run(conn)

        # flatten for output
        output = []
        for ebook in cursor:
            output.append({
                'ebook_id': ebook['ebook_id'],
                'file_hash': ebook['file_hash'],
                'format': ebook['format'],
            })

        if verify_s3 == True:
            # connect to S3
            s3 = connect_s3(self.config)
            bucket = s3.get_bucket(self.config['S3_BUCKET'])

            # verify books are on S3
            for b in output:
                # TODO rethink
                filename = self.generate_filename(b['file_hash'])
                k = boto.s3.key.Key(bucket, filename)
                self.set_uploaded(b['file_hash'])
                # TODO update rs when verify=True

        return output


class S3DatastoreError(Exception):
    pass
