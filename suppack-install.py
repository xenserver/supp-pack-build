#!/usr/bin/env python
# Copyright (c) 2012 Citrix Systems, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation; version 2.1 only. with the special
# exception on linking described in file LICENSE.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

"""XCP supplemental pack installer"""

from xcp.accessor import *
from xcp.environ import *
from xcp.repository import *
from xcp.version import *

import os.path
import shutil
import subprocess
import sys
import xml.dom.minidom

INSTALLED_REPOS_DIR = '/etc/xensource/installed-repos'

def _prompt(prompt, msg, ret):
    if msg:
        print msg
    while (True):
        k = raw_input(prompt)
        if len(k) > 0:
            if k.lower()[0] == 'n':
                sys.exit(ret)
            if k.lower()[0] == 'y':
                break

def prompt_continue(msg, ret):
    _prompt("Do you want to continue? (Y/N) ", msg, ret)

def prompt_accept(msg, ret):
    _prompt("Accept? (Y/N) ", msg, ret)
        
def md5sum_file(fname):
        digest = md5.new()
        fh = open(fname)
        while (True):
            blk = fh.read(8192)
            if len(blk) == 0:
                break
            digest.update(blk)
        fh.close()
        return digest.hexdigest()

try:
    a = FileAccessor('file://./', True)
    repo = Repository(a, '')
except:
    raise SystemExit, "Failed to parse pack metadata"

inventory = {}
try:
    fh = open("/etc/xensource-inventory")
    for line in fh:
        if not line.startswith('#') and '=' in line:
            k, v = line.strip().split('=', 1)
            if v[0] == "'":
                v = v[1:]
            if v[-1] == "'":
                v = v[:-1]
            inventory[k] = v
    fh.close()
except:
    raise SystemExit, "Cannot read inventory"

# check compatibility
if 'PRODUCT_BRAND' in inventory:
    match = False
    if inventory['PRODUCT_BRAND'] == repo.product:
        match = True
    elif 'PLATFORM_NAME' in inventory and inventory['PLATFORM_NAME'] == repo.product:
        match = True

    if not match:
        prompt_continue("Error: Repository is not compatible with installed product (%s expected)" % repo.product, 2)

# check if installed already
if os.path.exists(os.path.join(INSTALLED_REPOS_DIR, repo.identifier)):
    prompt_continue("Warning: '%s' is already installed" % repo.description, 3)

# check dependencies
a = FileAccessor('file://'+INSTALLED_REPOS_DIR+'/', True)
errors = False
for r in repo.requires:
    ri = r['originator']+':'+r['name']
    if not os.path.exists(os.path.join(INSTALLED_REPOS_DIR, ri)):
        raise SystemExit, "FATAL: missing dependency " + ri

    ver_str = r['version']
    if 'build' in r:
        ver_str += '-'+r['build']
    want_ver = version.Version.from_string(ver_str)
    
    d = Repository(a, ri)
    if not eval("d.product_version.__%s__(want_ver)" % r['test']):
        print "Error: unsatisfied dependency %s %s %s" % (ri, r['test'], ver_str)
        errors = True

if errors:
    prompt_continue(None, 2)

# check packages
fatal = False
for p in repo.packages:
    if os.path.exists(p.filename):
        if md5sum_file(p.filename) != p.md5sum:
            print "FATAL: MD5 mismatch on %s (expected %s)" % (p.filename, p.md5sum)
            fatal = True
    else:
        print "FATAL: %s missing" % p.filename
        fatal = True

if fatal:
    sys.exit(1)

# filter RPMs currently installed
install_list = []
upgrade_list = []
for p in filter(lambda x: isinstance(x, RPMPackage), repo.packages):
    pkg_name, _ = subprocess.Popen(['rpm', '--nosignature', '-q', '--qf', '%{NAME}',
                                    '-p', p.filename], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE).communicate()
    pkg_ver, _ = subprocess.Popen(['rpm', '--nosignature', '-q', '--qf', '%{VERSION}-%{RELEASE}',
                                    '-p', p.filename], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE).communicate()
    install = (pkg_name in ['kernel-xen', 'kernel-kdump'])
    s = subprocess.Popen(['rpm', '--nosignature', '-q', '--qf', '%{VERSION}-%{RELEASE}',
                          pkg_name], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    inst_ver, _ = s.communicate()
    if s.returncode != 0:
        if install:
            install_list.append(p)
        else:
            upgrade_list.append(p)
    elif pkg_ver != inst_ver:
        if install:
            install_list.append(p)
        else:
            upgrade_list.append(p)

print "Installing '%s'...\n" % repo.description

# display EULAs
for p in filter(lambda x: isinstance(x, RPMPackage), repo.packages):
    p1 = subprocess.Popen(['rpm2cpio', p.filename], stdout=subprocess.PIPE)
    p2 = subprocess.Popen(['cpio', '-i', '--to-stdout', '--quiet', '*EULA'],
                          stdin=p1.stdout, stdout=subprocess.PIPE)
    p1.stdout.close()
    text = p2.communicate()[0]
    if len(text) > 0:
        prompt_accept(text, 4)

# install packages
if len(install_list) > 0:
    s = subprocess.Popen(['rpm', '-ihv'] + map(lambda x: x.filename, install_list))
    _ = s.communicate()
    if s.returncode != 0:
        raise SystemExit, "FATAL: packages failed to install"
if len(upgrade_list) > 0:
    s = subprocess.Popen(['rpm', '-Uhv'] + map(lambda x: x.filename, upgrade_list))
    _ = s.communicate()
    if s.returncode != 0:
        raise SystemExit, "FATAL: packages failed to install"

# update metadata
try:
    try:
        os.mkdir(os.path.join(INSTALLED_REPOS_DIR, repo.identifier))
    except:
        pass
    shutil.copy(Repository.REPOSITORY_FILENAME,
                os.path.join(INSTALLED_REPOS_DIR, repo.identifier,
                             Repository.REPOSITORY_FILENAME))
    shutil.copy(Repository.PKGDATA_FILENAME,
                os.path.join(INSTALLED_REPOS_DIR, repo.identifier,
                             Repository.PKGDATA_FILENAME))
except:
    raise SystemExit, "FATAL: Failed to update metadata"

s = subprocess.Popen(['/opt/xensource/libexec/set-dom0-memory-target-from-packs'])
_ = s.communicate()
if s.returncode != 0:
    raise SystemExit, "FATAL: packages failed to update memory target"

i = readInventory()
host_uuid = i['INSTALLATION_UUID']
s = subprocess.Popen(['xe', 'host-refresh-pack-info', 'host-uuid='+host_uuid])
_ = s.communicate()
if s.returncode != 0:
    raise SystemExit, "FATAL: packages failed to update software versions"

print "Pack installation successful."
