# Override this to install docs somewhere else
DOCDIR = /usr/share/doc/packages
VERSION ?= $(shell (git describe --tags --long --match 'v*' 2>/dev/null || echo '0.0.0') | sed -e 's/^v//' -e 's/-/+/' -e 's/-/./')

CEPHFSSYNC_DEPS=rsync
PYTHON_DEPS=python3-setuptools python3-click python3-configobj python3-PyYAML
PYTHON_EXT_DEPS=
PYMOD_INSTALL=pip3 install
PYTHON=python3
OS=$(shell source /etc/os-release 2>/dev/null ; echo $$ID)
suse=
ifneq (,$(findstring opensuse,$(OS)))
suse=yes
endif
ifeq ($(OS), sles)
suse=yes
endif
ifeq ($(suse), yes)
USER=root
GROUP=root
PKG_INSTALL=zypper -n install
PYTHON_EXT_DEPS=parallel-ssh tox
else
USER=root
GROUP=root
ifeq ($(OS), centos)
PKG_INSTALL=yum install -y
PYMOD_INSTALL=$(PKG_INSTALL)
PYTHON_DEPS=python-setuptools python-click python-tox python-configobj python-PyYAML python-parallel-ssh
PYTHON=python
else
ifeq ($(OS), fedora)
PKG_INSTALL=yum install -y
else
debian := $(wildcard /etc/debian_version)
ifneq ($(strip $(debian)),)
PKG_INSTALL=apt-get install -y
endif
endif
endif
endif

usage:
	@echo "Usage:"
	@echo -e "\tmake install\tInstall CephFS_Sync on this host"
	@echo -e "\tmake rpm\tBuild an RPM for installation elsewhere"
	@echo -e "\tmake test\tRun unittests"

version:
	@echo "version: "$(VERSION)

setup.py:
	sed "s/DEVVERSION/"$(VERSION)"/" setup.py.in > setup.py

pyc: setup.py
	#make sure to create bytecode with the correct version
	find cli/ -name '*.py' -exec $(PYTHON) -m py_compile {} \;

copy-files:
	# docs
	install -d -m 755 $(DESTDIR)$(DOCDIR)/cephfs_sync
	install -m 644 LICENSE $(DESTDIR)$(DOCDIR)/cephfs_sync/
	install -m 644 README.md $(DESTDIR)$(DOCDIR)/cephfs_sync/
	# examples
	install -d -m 755 $(DESTDIR)$(DOCDIR)/cephfs_sync/examples
	install -m 644 doc/examples/* $(DESTDIR)$(DOCDIR)/cephfs_sync/examples/

	# man pages
	install -d -m 755 $(DESTDIR)/usr/share/man/man1
	install -m 644 man/cephfs_sync*.1 $(DESTDIR)/usr/share/man/man1

	# At runtime, these need to be owned by root:root.  This won't work
	# in a buildroot on OBS, hence the leading '-' to ignore failures
	# and '|| true' to suppress some error output, but will work fine
	# in development when root runs `make install`.
	#-chown $(USER):$(GROUP) $(DESTDIR)/destdir || true

install-deps:
	# Using '|| true' to suppress failure (packages already installed, etc)
	$(PKG_INSTALL) $(CEPHFSSYNC_DEPS) || true
	$(PKG_INSTALL) $(PYTHON_DEPS) || true
	$(if $(strip $(PYTHON_EXT_DEPS)), $(PYMOD_INSTALL) $(PYTHON_EXT_DEPS),)

install: pyc install-deps copy-files
	# cephfs_sync-cli
	$(PYTHON) setup.py install --root=$(DESTDIR)/
	install -m 755 cli/cephfs_sync $(DESTDIR)/usr/bin

rpm: tarball
	sed '/^Version:/s/[^ ]*$$/'$(VERSION)'/' cephfs_sync.spec.in > cephfs_sync.spec
	rpmbuild -bb cephfs_sync.spec

# Removing test dependency until resolved
tarball:
	$(eval TEMPDIR := $(shell mktemp -d))
	mkdir $(TEMPDIR)/cephfs_sync-$(VERSION)
	git archive HEAD | tar -x -C $(TEMPDIR)/cephfs_sync-$(VERSION)
	sed "s/DEVVERSION/"$(VERSION)"/" $(TEMPDIR)/cephfs_sync-$(VERSION)/setup.py.in > $(TEMPDIR)/cephfs_sync-$(VERSION)/setup.py
	sed "s/DEVVERSION/"$(VERSION)"/" $(TEMPDIR)/cephfs_sync-$(VERSION)/cephfs_sync.spec.in > $(TEMPDIR)/cephfs_sync-$(VERSION)/cephfs_sync.spec
	mkdir -p ~/rpmbuild/SOURCES
	cp $(TEMPDIR)/cephfs_sync-$(VERSION)/setup.py .
	tar -cjf ~/rpmbuild/SOURCES/cephfs_sync-$(VERSION).tar.bz2 -C $(TEMPDIR) .
	rm -r $(TEMPDIR)

test: setup.py
	tox -e py3

lint: setup.py
	tox -e lint
