AWS_ACCESS_KEY_ID?=error
AWS_SECRET_ACCESS_KEY?=error
AWS_DEFAULT_REGION?=local
ENV?=dev
AWSCLI?=/usr/local/bin/aws


clean:
	@rm -rf dist/ogreclient-* ogreclient.egg-info build dedrm

dist: clean build-dedrm
	python setup.py sdist --formats=gztar,zip

release: dist
	cd dist && \
		$(AWSCLI) s3 cp . s3://ogre-dist-$(ENV)-$(AWS_DEFAULT_REGION) --recursive --exclude "*" --include "ogreclient-*" --acl=public-read
	$(AWSCLI) s3 cp dedrm/dist/dedrm-*.tar.gz s3://ogre-dist-$(ENV)-$(AWS_DEFAULT_REGION) --acl=public-read

build-dedrm:
	git clone --branch ogre https://github.com/oii/DeDRM_tools.git dedrm
	cd dedrm && \
		python setup.py sdist

clean-bitbar:
	@rm -rf dist/BitBar*.{zip,app} dist/bitbar-bundler

fetch-bitbar: clean-bitbar
	@cd dist && \
		curl -O https://raw.githubusercontent.com/matryer/bitbar/master/Scripts/bitbar-bundler && \
		chmod u+x bitbar-bundler && \
		curl -O -L https://github.com/matryer/bitbar/releases/download/v2.0.0-beta10/BitBarDistro-v2.0.0-beta10.zip && \
		unzip -q BitBarDistro-v2.0.0-beta10.zip

package-bitbar: fetch-bitbar
	@cd dist && \
		./bitbar-bundler BitBarDistro.app bitbar-ogreclient.1d.sh
	@cd dist && \
		zip -rq9ym BitBarDistro.zip BitBarDistro.app

push-bitbar-s3:
	$(AWSCLI) s3 cp dist/BitBarDistro.zip s3://ogre-dist-$(ENV)-$(AWS_DEFAULT_REGION) --acl=public-read


.PHONY: clean dist build-dedrm clean-bitbar fetch-bitbar package-bitbar push-bitbar-s3
