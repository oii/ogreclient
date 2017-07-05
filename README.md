===== Distributing Ogreclient =====

==== Simple ====

Run the following command, which will build ogreclient and dedrm distributions:

    make dist

Alternatively the following command will build and push to S3 for use in staging/production. Note the supplied environment vars - you will also need `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` exported:

    ENV=staging AWS_DEFAULT_REGION=eu-west-1 make release


==== Detailed ====

The normal Python setuptools method will create a source distribution that is cross-platform compatible.
The actual command for this is in the `Makefile`, as part of the `dist` command.

=== OSX ===





==== Testing ====

The dist directory contains two Vagrant projects, one for OSX and one for Windows. These enable us
to test the client install scripts on each client OS.
