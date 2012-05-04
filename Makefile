USE_BRANDING := yes
IMPORT_BRANDING := yes
REPONAME := supp-pack-build
DIRNAME := xcp
include $(B_BASE)/common.mk
include $(B_BASE)/rpmbuild.mk

-include $(MY_OBJ_DIR)/version.inc
.PHONY: $(MY_OBJ_DIR)/version.inc
$(MY_OBJ_DIR)/version.inc:
	$(version-makefile) > $@
	$(call hg_cset_number,$(REPONAME)) >> $@
	echo SUPP_PACK_BUILD_VERSION := \$$\(PLATFORM_VERSION\) >> $@
	echo SUPP_PACK_BUILD_RELEASE := xs\$$\(CSET_NUMBER\) >> $@

SUPP_PACK_BUILD_SOURCES := $(wildcard *.py)

SUPP_PACK_BUILD_SPEC := supp-pack-build.spec
SUPP_PACK_BUILD_SRC_DIR := supp-pack-build-$(SUPP_PACK_BUILD_VERSION)
SUPP_PACK_BUILD_SRC := $(RPM_SOURCESDIR)/supp-pack-build-$(SUPP_PACK_BUILD_VERSION).tar.gz
SUPP_PACK_BUILD_SRPM := supp-pack-build-$(SUPP_PACK_BUILD_VERSION)-$(SUPP_PACK_BUILD_RELEASE).src.rpm
SUPP_PACK_BUILD_STAMP := $(MY_OBJ_DIR)/.rpmbuild.supp_pack_build.stamp

.PHONY: build
build: $(SUPP_PACK_BUILD_STAMP) $(MY_OUTPUT_DIR)/supp-pack-build.inc $(MY_SOURCES)/MANIFEST

$(MY_SOURCES)/MANIFEST: $(MY_SOURCES_DIRSTAMP) $(RPM_BUILD_COOKIE)
	( echo "$(COMPONENT) gpl file $(RPM_SRPMSDIR)/$(SUPP_PACK_BUILD_SRPM)" ; \
	) >$@

$(MY_OUTPUT_DIR)/supp-pack-build.inc: $(MY_OUTPUT_DIR)/.dirstamp
	( echo SUPP_PACK_BUILD_PKG_NAME := supp-pack-build ;\
	  echo SUPP_PACK_BUILD_PKG_VERSION := $(SUPP_PACK_BUILD_VERSION)-$(SUPP_PACK_BUILD_RELEASE) ;\
	  echo SUPP_PACK_BUILD_PKG_FILE := RPMS/noarch/supp-pack-build-$(SUPP_PACK_BUILD_VERSION)-$(SUPP_PACK_BUILD_RELEASE).noarch.rpm ;\
	) >$@

.PHONY: pylint
pylint:
	run-pylint.sh $(SUPP_PACK_BUILD_SOURCES)

.PHONY: sources
sources: $(MY_SOURCES)/MANIFEST

.PHONY: clean
clean:
	rm -f $(SUPP_PACK_BUILD_STAMP) $(SUPP_PACK_BUILD_SRC) $(RPM_SPECSDIR)/$(SUPP_PACK_BUILD_SPEC)

.SECONDARY: $(SUPP_PACK_BUILD_SRC)
$(SUPP_PACK_BUILD_SRC): $(SUPP_PACK_BUILD_SOURCES)
	$(call mkdir_clean,$(MY_OBJ_DIR)/$(SUPP_PACK_BUILD_SRC_DIR))
	mkdir -p $(MY_OBJ_DIR)/$(SUPP_PACK_BUILD_SRC_DIR)/$(DIRNAME)
	mkdir -p $(MY_OBJ_DIR)/$(SUPP_PACK_BUILD_SRC_DIR)/scripts
	cp -f setup.py $(MY_OBJ_DIR)/$(SUPP_PACK_BUILD_SRC_DIR)
	cp -f supplementalpack.py $(MY_OBJ_DIR)/$(SUPP_PACK_BUILD_SRC_DIR)/$(DIRNAME)
	cp -f build-supplemental-pack.py $(MY_OBJ_DIR)/$(SUPP_PACK_BUILD_SRC_DIR)/scripts
	cp -f suppack-install.py $(MY_OBJ_DIR)/$(SUPP_PACK_BUILD_SRC_DIR)/scripts
	cp -f suppack-install.sh $(MY_OBJ_DIR)/$(SUPP_PACK_BUILD_SRC_DIR)/scripts
	echo -e "#!/bin/sh\nexec \$${0%.sh}.py \"\$$@\"" >$(MY_OBJ_DIR)/$(SUPP_PACK_BUILD_SRC_DIR)/scripts/build-supplemental-pack.sh
	tar zcf $@ -C $(MY_OBJ_DIR) $(SUPP_PACK_BUILD_SRC_DIR)
	rm -rf $(MY_OBJ_DIR)/$(SUPP_PACK_BUILD_SRC_DIR)

.SECONDARY: $(RPM_SPECSDIR)/%.spec
$(RPM_SPECSDIR)/%.spec: *.spec.in
	sed -e 's/@SUPP_PACK_BUILD_VERSION@/$(SUPP_PACK_BUILD_VERSION)/g' \
	  -e 's/@SUPP_PACK_BUILD_RELEASE@/$(SUPP_PACK_BUILD_RELEASE)/g' \
	  < $< \
	  > $@

$(RPM_SRPMSDIR)/$(SUPP_PACK_BUILD_SRPM): $(RPM_DIRECTORIES) $(RPM_SPECSDIR)/$(SUPP_PACK_BUILD_SPEC) $(SUPP_PACK_BUILD_SRC)
	$(RPMBUILD) -bs $(RPM_SPECSDIR)/$(SUPP_PACK_BUILD_SPEC)

$(SUPP_PACK_BUILD_STAMP): $(RPM_SRPMSDIR)/$(SUPP_PACK_BUILD_SRPM)
	# work around rpmbuild removing source and spec
	ln -f $(RPM_SPECSDIR)/$(SUPP_PACK_BUILD_SPEC) $(RPM_SPECSDIR)/$(SUPP_PACK_BUILD_SPEC).keep
	ln -f $(SUPP_PACK_BUILD_SRC) $(SUPP_PACK_BUILD_SRC).keep
	$(RPMBUILD) --define "dirname $(DIRNAME)" --rebuild $(RPM_SRPMSDIR)/$(SUPP_PACK_BUILD_SRPM)
	mv -f $(RPM_SPECSDIR)/$(SUPP_PACK_BUILD_SPEC).keep $(RPM_SPECSDIR)/$(SUPP_PACK_BUILD_SPEC)
	mv -f $(SUPP_PACK_BUILD_SRC).keep $(SUPP_PACK_BUILD_SRC)
	mkdir -p $(MY_OUTPUT_DIR)/INSTALL
	ln -f $(MY_OUTPUT_DIR)/RPMS/noarch/supp-pack-build-$(SUPP_PACK_BUILD_VERSION)-$(SUPP_PACK_BUILD_RELEASE).noarch.rpm \
		$(MY_OUTPUT_DIR)/INSTALL
	touch $@
