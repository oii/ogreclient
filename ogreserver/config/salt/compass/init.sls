compass-rubygems:
  pkg.installed:
    - name: rubygems

compass-gem:
  gem.installed:
    - name: compass
    - require:
      - pkg: compass-rubygems

compass-supervisor-config:
  file.managed:
    - name: /etc/supervisor/conf.d/compass.{{ pillar['app_name'] }}.conf
    - source: salt://compass/supervisord.conf
    - template: jinja
    - default:
        directory: /srv/{{ pillar['app_name'] }}
    - require:
      - gem: compass-gem
    - require_in:
      - service: supervisor

compass-supervisor-service:
  supervisord.running:
    - name: {{ pillar['app_name'] }}.compass
    - update: true
    - require:
      - service: supervisor
    - watch:
      - file: compass-supervisor-config
