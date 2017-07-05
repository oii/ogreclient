from __future__ import absolute_import
from __future__ import unicode_literals

import json
import os
import sqlite3

from .ebook_obj import EbookObject
from .exceptions import OgreException, MissingFromCacheError, EbookIdDuplicateEbookError
from .printer import CliPrinter

__CACHEVERSION__ = 1


prntr = CliPrinter.get_printer()


class Cache:
    def __init__(self, config, ebook_cache_path):
        self.config = config
        self.ebook_cache_path = ebook_cache_path


    def verify_cache(self):
        must_init_cache = False

        if os.path.exists(self.ebook_cache_path):
            conn = None
            try:
                # check the cache is valid
                conn = sqlite3.connect(self.ebook_cache_path)
                c = conn.cursor()
                c.execute('SELECT version FROM meta LIMIT 1')

                # if no exception thus far, check the cache version
                version = c.fetchone()[0]
                if version < __CACHEVERSION__:
                    # migrate cache model as upgrade path
                    self.cache_migrate(version, __CACHEVERSION__)

            except:
                prntr.error('Cache file corrupt! Recreating as per first run..')
                must_init_cache = True
            finally:
                if conn is not None:
                    conn.close()
        else:
            # first create of cache db
            must_init_cache = True

        if must_init_cache:
            # create the sqlite cache
            self.init_cache()

        return must_init_cache


    def cache_migrate(self, from_version, to_version):
        pass


    def init_cache(self):
        conn = sqlite3.connect(self.ebook_cache_path)
        try:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE ebooks (
                      path TEXT PRIMARY KEY,
                      file_hash TEXT NULL,
                      ebook_id TEXT,
                      data TEXT NULL,
                      drmfree INT DEFAULT 0,
                      skip INT DEFAULT 0
                )'''
            )
            c.execute('CREATE TABLE meta (version INT PRIMARY KEY)')
            conn.commit()
            c.execute('INSERT INTO meta VALUES (?)', (__CACHEVERSION__,))
            conn.commit()
        except Exception as e:
            raise CacheInitError(inner_excp=e)
        finally:
            conn.close()


    def get_ebook(self, path, file_hash=None):
        conn = sqlite3.connect(self.ebook_cache_path)
        try:
            c = conn.cursor()
            c.execute('SELECT file_hash, ebook_id, data, drmfree, skip FROM ebooks WHERE path = ?', (path,))
            obj = c.fetchone()
            if obj is not None:
                # verify file_hash matches between cache and filesystem
                if file_hash is not None and obj[0] != file_hash:
                    c.execute('DELETE FROM ebooks WHERE path = ?', (path,))
                    conn.commit()
                    raise MissingFromCacheError
            else:
                raise MissingFromCacheError

        except MissingFromCacheError as e:
            raise e
        except Exception as e:
            raise CacheReadError(inner_excp=e)
        finally:
            conn.close()

        return EbookObject.deserialize(self.config, path, obj)


    def store_ebook(self, ebook_obj):
        # serialize the ebook object for storage
        data = ebook_obj.serialize(for_cache=True)

        conn = sqlite3.connect(self.ebook_cache_path)
        try:
            c = conn.cursor()
            c.execute('SELECT drmfree FROM ebooks WHERE path = ?', (ebook_obj.path,))
            obj = c.fetchone()
            # update if exists, otherwise insert
            if obj is not None:
                values = ''
                params = []

                # build update parameter list
                values += 'file_hash = ?, '
                params.append(ebook_obj.file_hash)
                values += 'ebook_id = ?, '
                params.append(ebook_obj.ebook_id)
                values += 'data = ?, '
                params.append(json.dumps(data))
                values += 'drmfree = ?, '
                params.append(int(ebook_obj.drmfree))
                values += 'skip = ?'
                params.append(int(ebook_obj.skip))

                # where path
                params.append(ebook_obj.path)

                c.execute(
                    'UPDATE ebooks SET {} WHERE path = ?'.format(values), params
                )
            else:
                params = (
                    ebook_obj.path,
                    ebook_obj.file_hash,
                    ebook_obj.ebook_id,
                    json.dumps(data),
                    int(ebook_obj.drmfree),
                    int(ebook_obj.skip)
                )
                c.execute('INSERT INTO ebooks VALUES (?,?,?,?,?,?)', params)

            # write the cache DB
            conn.commit()

        except sqlite3.IntegrityError as e:
            if e.message == 'UNIQUE constraint failed: ebooks.ebook_id':
                # ebook_id UNIQUE failure; load the existing book from the cache
                c = conn.cursor()
                c.execute('SELECT path FROM ebooks WHERE ebook_id = ?', (ebook_obj.ebook_id,))
                obj = c.fetchone()
                raise EbookIdDuplicateEbookError(ebook_obj, obj[0])
            else:
                raise CacheReadError(inner_excp=e)
        except Exception as e:
            raise CacheReadError(inner_excp=e)
        finally:
            conn.close()


    def update_ebook_property(self, path, file_hash=None, ebook_id=None, drmfree=None, skip=None):
        conn = sqlite3.connect(self.ebook_cache_path)
        try:
            c = conn.cursor()
            c.execute('SELECT drmfree FROM ebooks WHERE path = ?', (path,))
            obj = c.fetchone()
            if obj is None:
                raise MissingFromCacheError
            else:
                values = ''
                params = []

                # build update parameter list
                if file_hash is not None:
                    values += 'file_hash = ?, '
                    params.append(file_hash)

                if ebook_id is not None:
                    values += 'ebook_id = ?, '
                    params.append(ebook_id)

                if drmfree is not None:
                    values += 'drmfree = ?, '
                    params.append(int(drmfree))

                if skip is not None:
                    values += 'skip = ?, '
                    params.append(int(skip))

                # drop trailing comma
                values = values[:-2]

                # where path
                params.append(path)

                c.execute(
                    'UPDATE ebooks SET {} WHERE path = ?'.format(values), params
                )
                conn.commit()
        except Exception as e:
            raise CacheReadError(inner_excp=e)
        finally:
            conn.close()


class CacheInitError(OgreException):
    pass

class CacheReadError(OgreException):
    pass

class CacheWriteError(OgreException):
    pass
