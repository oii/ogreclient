from __future__ import unicode_literals


class OgreException(Exception):
    def __init__(self, message=None, inner_excp=None):
        super(OgreException, self).__init__(message)
        self.inner_excp = inner_excp

class OgreWarning(Exception):
    def __init__(self, message=None):
        super(OgreWarning, self).__init__(message)

class ConfigSetupError(OgreException):
    pass

class AuthDeniedError(OgreException):
    pass

class AuthError(OgreException):
    pass

class OgreserverDownError(OgreException):
    def __init__(self):
        super(OgreserverDownError, self).__init__('Please try again later :(')

class NoEbooksError(OgreWarning):
    def __init__(self):
        super(NoEbooksError, self).__init__('No ebooks found.. Cannot continue!')

class NoUploadsError(OgreException):
    pass

class BaconError(OgreException):
    pass

class MushroomError(OgreException):
    pass

class SpinachError(OgreException):
    pass

class CorruptEbookError(OgreException):
    pass

class FailedWritingMetaDataError(OgreException):
    pass

class FailedConfirmError(OgreException):
    pass

class FailedDebugLogsError(OgreException):
    pass

class KindlePrereqsError(OgreException):
    pass

class NoEbookSourcesFoundError(OgreException):
    pass


class DuplicateEbookBaseError(OgreWarning):
    def __init__(self, kind, ebook_obj, path2):
        super(DuplicateEbookBaseError, self).__init__(
            u"Duplicate ebook found ({}) '{}':\n  {}\n  {}".format(kind, ebook_obj.path, path2)
        )

class ExactDuplicateEbookError(DuplicateEbookBaseError):
    def __init__(self, ebook_obj, path2):
        super(ExactDuplicateEbookError, self).__init__('exact', ebook_obj, path2)

class AuthortitleDuplicateEbookError(DuplicateEbookBaseError):
    def __init__(self, ebook_obj, path2):
        super(AuthortitleDuplicateEbookError, self).__init__('author/title', ebook_obj, path2)


class MissingFromCacheError(OgreException):
    pass
