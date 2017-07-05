Distributing Ogreclient
=======================

Binaries are now build with [pyinstaller](http://pyinstaller.readthedocs.io/en/stable), in order to
create a single executable.


Prerequisites
-------------

 * awscli
 * virtualenv (for python2)


Building for OSX
----------------

To build the pyinstaller binary for OSX, run the following (on an OSX machine):

    make pyinstaller

To build just the ogreclient and dedrm python dists:

    make dist

To build and push to S3 for use in staging/production. Note the environment vars - you will need
`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` exported:

    ENV=staging AWS_DEFAULT_REGION=eu-west-1 make release


### BitBar

    make package-bitbar
    ENV=staging AWS_DEFAULT_REGION=eu-west-1 make push-bitbar-s3


### BitBar menubar icon

    base64 ogreserver/static/images/ogreb-icon.png | pbcopy


Building for Windows
--------------------

TBD


Testing
-------

The dist directory contains two Vagrant projects, one for OSX and one for Windows. These enable us
to test the client install scripts on each client OS.

    export OGRE_ENDPOINT=http://192.168.1.131
    curl $OGRE_HOST/install | bash && ogre init
