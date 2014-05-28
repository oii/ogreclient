from __future__ import absolute_import

# import Flask-Login
from flask.ext.login import LoginManager


def init_app(app):
    login_manager = LoginManager()
    login_manager.setup_app(app)

    @login_manager.user_loader
    def load_user(userid):
        from ogreserver.models.user import User
        user = User.query.filter_by(id=int(userid)).first()
        return user

    return login_manager
