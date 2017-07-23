from __future__ import absolute_import
from __future__ import unicode_literals

import os
import shutil

from ogreclient import exceptions
from ogreclient.core.ebook_obj import EbookObject
from ogreclient.utils import make_temp_directory
from ogreclient.utils.dedrm import decrypt, DRM
from ogreclient.utils.printer import CliPrinter


prntr = CliPrinter.get_printer()


def clean_all_drm(config, ebooks_by_authortitle, ebooks_by_filehash):
    errord_list = []

    i = 0
    cleaned = 0
    bad_key_count = 0

    prntr.info('Ebook directory is {}'.format(config['ebook_home']))
    prntr.info('Decrypting DRM..')

    for authortitle, ebook_obj in ebooks_by_authortitle.iteritems():
        if bad_key_count > 3:
            raise exceptions.AbortSyncDueToBadKey

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
        except exceptions.DeDrmMissingError as e:
            errord_list.append(exceptions.DeDrmMissingError(ebook_obj))
            continue
        except exceptions.IncorrectKeyFoundError as e:
            bad_key_count += 1
            errord_list.append(e)
            continue
        except (exceptions.CorruptEbookError, exceptions.DecryptionFailed) as e:
            errord_list.append(e)
            continue

        if config['verbose'] is False:
            i += 1
            prntr.progressf(num_blocks=i, total_size=len(ebooks_by_authortitle))

    if cleaned > 0:
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

            if state in (DRM.none, DRM.decrypted):
                # create new ebook_obj for decrypted ebook
                decrypted_ebook_obj = EbookObject(
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

                if state == DRM.none:
                    # update cache to mark book as drmfree
                    config['ebook_cache'].update_ebook_property(ebook_obj.path, drmfree=True)
                else:
                    # update existing DRM-scuppered book as skip=True in cache
                    config['ebook_cache'].update_ebook_property(ebook_obj.path, skip=True)

            else:
                # mark book as having DRM
                config['ebook_cache'].update_ebook_property(ebook_obj.path, drmfree=False)

                if state == DRM.wrong_key:
                    raise exceptions.DecryptionFailed(ebook_obj, 'Incorrect key found for ebook')
                elif state == DRM.corrupt:
                    raise exceptions.DecryptionFailed(ebook_obj, 'Corrupt ebook found')
                elif state == DRM.kfxformat:
                    raise exceptions.DecryptionFailed(ebook_obj, 'KFX format ebooks are currently unsupported')
                else:
                    raise exceptions.DecryptionFailed(ebook_obj, 'Unknown error in decryption ({})'.format(str(state)))

    except UnicodeDecodeError as e:
        raise exceptions.CorruptEbookError(ebook_obj, 'Unicode filename problem', inner_excp=e)

    return decrypted_ebook_obj
