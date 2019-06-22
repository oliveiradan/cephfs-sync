# Override this to install docs somewhere else
DOCDIR = /usr/share/doc/packages
VERSION ?= $(shell (git describe --tags --long --match 'v*' 2>/dev/null || echo '0.0.0') | sed -e 's/^v//' -e 's/-/+/' -e 's/-/./')

CEPHFSSYNC_DEPS=rsync
PYTHON_DEPS=python3-setuptools python3-click python3-tox python3-configobj python3-PyYAML python3-parallel-ssh
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
else
USER=root
GROUP=root
ifeq ($(OS), centos)
PKG_INSTALL=yum install -y
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
	install -d -m 755 $(DESTDIR)$(DOCDIR)/cephfssync
	install -m 644 LICENSE $(DESTDIR)$(DOCDIR)/cephfssync/
	install -m 644 README.md $(DESTDIR)$(DOCDIR)/cephfssync/
	# examples
	install -d -m 755 $(DESTDIR)$(DOCDIR)/cephfssync/examples
	install -m 644 doc/examples/* $(DESTDIR)$(DOCDIR)/cephfssync/examples/

	# man pages
	install -d -m 755 $(DESTDIR)/usr/share/man/man1
	install -m 644 man/cephfssync*.1 $(DESTDIR)/usr/share/man/man1

	# state files - orchestrate stage symlinks
	#ln -sf prep		$(DESTDIR)/srv/salt/ceph/stage/0

	# At runtime, these need to be owned by salt:salt.  This won't work
	# in a buildroot on OBS, hence the leading '-' to ignore failures
	# and '|| true' to suppress some error output, but will work fine
	# in development when root runs `make install`.
	#-chown $(USER):$(GROUP) $(DESTDIR)/srv/salt/ceph/admin/cache || true

install-deps:
	# Using '|| true' to suppress failure (packages already installed, etc)
	$(PKG_INSTALL) $(CEPHFSSYNC_DEPS) || true
	$(PKG_INSTALL) $(PYTHON_DEPS) || true

install: pyc install-deps copy-files
	# cephfssync-cli
	$(PYTHON) setup.py install --root=$(DESTDIR)/

rpm: tarball
	sed '/^Version:/s/[^ ]*$$/'$(VERSION)'/' cephfs_sync.spec.in > cephfs_sync.spec
	rpmbuild -bb cephfs_sync.spec

# Removing test dependency until resolved
tarball:
	$(eval TEMPDIR := $(shell mktemp -d))
	mkdir $(TEMPDIR)/cephfssync-$(VERSION)
	git archive HEAD | tar -x -C $(TEMPDIR)/cephfssync-$(VERSION)
	sed "s/DEVVERSION/"$(VERSION)"/" $(TEMPDIR)/cephfssync-$(VERSION)/setup.py.in > $(TEMPDIR)/cephfssync-$(VERSION)/setup.py
	sed "s/DEVVERSION/"$(VERSION)"/" $(TEMPDIR)/cephfssync-$(VERSION)/cephfssync.spec.in > $(TEMPDIR)/cephfssync-$(VERSION)/cephfssync.spec
	mkdir -p ~/rpmbuild/SOURCES
	cp $(TEMPDIR)/cephfssync-$(VERSION)/setup.py .
	tar -cjf ~/rpmbuild/SOURCES/cephfssync-$(VERSION).tar.bz2 -C $(TEMPDIR) .
	rm -r $(TEMPDIR)

test: setup.py
	tox -e py3

lint: setup.py
	tox -e lint
