from __future__ import absolute_import
from __future__ import unicode_literals

from flask import current_app as app

from flask.ext.security.utils import url_for_security

from .tasks import convert, query_ebook_metadata, send_mail, store_ebook


def when_store_ebook(sender, ebook_id, filename, file_hash, fmt, username):
    store_ebook.delay(ebook_id, filename, file_hash, fmt, username)

def when_convert_ebook(sender, ebook_id, version_id, original_filename, dest_fmt):
    convert.delay(ebook_id, version_id, original_filename, dest_fmt)

def when_ebook_created(sender, ebook_data):
    query_ebook_metadata.delay(ebook_data)


def when_password_reset(sender, user, **extra):
    send_mail.delay(
        recipient=user.email,
        subject=app.config['EMAIL_SUBJECT_PASSWORD_NOTICE'],
        template='reset_notice',
        user=user
    )

def when_password_changed(sender, user, **extra):
    forgot_link = url_for_security('forgot_password', _external=True)

    send_mail.delay(
        recipient=user.email,
        subject=app.config['EMAIL_SUBJECT_PASSWORD_CHANGE_NOTICE'],
        template='change_notice',
        user=user,
        forgot_link=forgot_link
    )

def when_reset_password_sent(sender, token, user, **extra):
    reset_link = url_for_security('reset_password', token=token, _external=True)

    send_mail.delay(
        recipient=user.email,
        subject=app.config['SECURITY_EMAIL_SUBJECT_PASSWORD_RESET'],
        template='reset_instructions',
        user=user,
        reset_link=reset_link
    )

def when_confirm_instructions_sent(sender, token, user, **extra):
    confirmation_link = url_for_security('confirm_email', token=token, _external=True)

    send_mail.delay(
        recipient=user.email,
        subject=app.config['EMAIL_SUBJECT_CONFIRM'],
        template='confirmation_instructions',
        user=user,
        confirmation_link=confirmation_link
    )
