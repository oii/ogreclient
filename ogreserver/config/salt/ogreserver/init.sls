include:
  - app.virtualenv
  - app.source
  - app.supervisor
  - calibre
  - closure-compiler
  - compass
  - github
  - gunicorn
  - mysql
  - nodejs
  - pypiserver
  - rabbitmq
  - rabbitmq.celerybeat
  - rethinkdb


extend:
  gunicorn-config:
    file.managed:
      - context:
          worker_class: gevent
          gunicorn_port: {{ pillar['gunicorn_port'] }}

  app-virtualenv:
    virtualenv.managed:
      - requirements: /srv/{{ pillar['app_directory_name'] }}/ogreserver/config/requirements.txt
      - require:
        - pkg: pip-dependencies-extra
        - git: git-clone-app

  /etc/supervisor/conf.d/ogreserver.conf:
    file.managed:
      - context:
          workers:
            high: 0
            normal: 0
            low: 1

  ogreserver-supervisor-service:
    supervisord.running:
      - require:
        - cmd: rabbitmq-server-running
      - watch:
        - file: /etc/supervisor/conf.d/{{ pillar['app_name'] }}.conf
        - file: /etc/gunicorn.d/{{ pillar['app_name'] }}.conf.py

  pypiserver-log-dir:
    file.directory:
      - user: {{ pillar['app_user'] }}
      - group: {{ pillar['app_user'] }}

  pypiserver-supervisor-config:
    file.managed:
      - context:
          port: 8233
          runas: {{ pillar['app_user'] }}


# install bower.io for Foundation 5
bower:
  npm.installed:
    - require:
      - cmd: npm-install

bower-ogreserver-install:
  cmd.run:
    - name: bower install --config.interactive=false
    - cwd: /srv/{{ pillar['app_directory_name'] }}/ogreserver/static
    - user: {{ pillar['app_user'] }}
    - unless: test -d /srv/{{ pillar['app_directory_name'] }}/ogreserver/static/bower_components
    - require:
      - git: git-clone-app

# compile sass to css
sass-compile:
  cmd.run:
    - name: compass compile --force --boring
    - cwd: /srv/{{ pillar['app_directory_name'] }}/ogreserver/static
    - user: {{ pillar['app_user'] }}
    - require:
      - git: git-clone-app
      - gem: compass-gem
      - cmd: bower-ogreserver-install


pip-dependencies-extra:
  pkg.latest:
    - names:
      - libmysqlclient-dev
      - libevent-dev

flask-config-dir:
  file.directory:
    - name: /etc/ogre
    - user: {{ pillar['app_user'] }}
    - group: {{ pillar['app_user'] }}

flask-config:
  file.managed:
    - name: /etc/ogre/flask.app.conf.py
    - source: salt://ogreserver/flask.app.conf.py
    - template: jinja
    - user: {{ pillar['app_user'] }}
    - group: {{ pillar['app_user'] }}
    - require:
      - git: git-clone-app
      - file: flask-config-dir
    - require_in:
      - service: supervisor

ogre-init:
  cmd.run:
    - name: /home/{{ pillar['app_user'] }}/.virtualenvs/{{ pillar['app_name'] }}/bin/python manage.py init_ogre
    - cwd: /srv/ogre
    - unless: /home/{{ pillar['app_user'] }}/.virtualenvs/{{ pillar['app_name'] }}/bin/python manage.py init_ogre --test
    - user: {{ pillar['app_user'] }}
    - require:
      - virtualenv: app-virtualenv
      - file: flask-config
      - mysql_grants: create-mysql-user-perms
      - pip: rethinkdb-python-driver

# build dedrm and stick it in the pypiserver cache
build-dedrm:
  cmd.run:
    - name: python setup.py sdist
    - cwd: /srv/ogre/dedrm
    - require:
      - git: git-clone-app
  file.rename:
    - name: /var/pypiserver-cache/dedrm-6.0.7.tar.gz
    - source: /srv/ogre/dedrm/dist/dedrm-6.0.7.tar.gz
    - force: true
    - require:
      - file: pypiserver-package-dir
    - watch:
      - cmd: build-dedrm
