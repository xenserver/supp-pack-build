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

"""supplementalpack - create XCP supplemental packs"""

import warnings
warnings.simplefilter("ignore", DeprecationWarning)

from optparse import OptionParser

import md5
import os
import os.path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import xml.dom.minidom

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

class Package:
    # allow creation of bzipped tar packages
    permit_legacy = False

    def __init__(self, fname):
        self.fname = fname
        try:
            self.size = str(os.stat(fname).st_size)
        except:
            raise SystemExit, "Cannot open " + fname
        self.md5 = md5sum_file(fname)

        filetype = subprocess.Popen(['file', '-k', '-b', fname],
                                    stdout=subprocess.PIPE).communicate()[0]
        if re.search('RPM', filetype):
            rpmname = subprocess.Popen(['rpm', '--nosignature', '-q', '--qf', '%{NAME}',
                                        '-p', fname], stdout=subprocess.PIPE).communicate()[0]
            rpmgroup = subprocess.Popen(['rpm', '--nosignature', '-q', '--qf', '%{GROUP}',
                                         '-p', fname], stdout=subprocess.PIPE).communicate()[0]
            if rpmgroup.endswith('/Kernel'):
                self.type = 'driver-rpm'
                m = re.search('(.*)-modules-([^-]*)-(.*)', rpmname)
                if m:
                    self.label = m.group(1)
                    self.kernel = m.group(3) + m.group(2)
                else:
                    self.label = rpmname
                    self.kernel = 'any'
            else:
                self.type = 'rpm'
                self.label = rpmname
        elif re.search('bzip2', filetype):
            self.type = 'tbz2'
            self.label = os.path.basename(fname)
        else:
            self.type = 'unknown'

    # validate a package
    def check(self):
        if self.type == 'unknown' or (self.type == 'tbz2' and not self.permit_legacy):
            raise SystemExit, "Error: unsupported package type " + self.fname

        if self.type == 'rpm':
            p = subprocess.Popen(['rpm', '--nosignature', '-qlp', self.fname],
                                 stdout=subprocess.PIPE)
            while True:
                l = p.stdout.readline().strip()
                if len(l) == 0:
                    break
                if l.startswith('/lib/modules/') or l.startswith('/boot/vmlinu'):
                    raise SystemExit, "Error: unsupported file %s in %s" % (l, self.fname)
            p.wait()
        elif self.type == 'driver-rpm':
            if self.flavour() not in ('any', 'kdump', 'xen'):
                raise SystemExit, "Error: unexpected kernel suffix (%s)" % self.kernel
            p = subprocess.Popen(['rpm', '--nosignature', '-qlp', self.fname],
                                 stdout=subprocess.PIPE)
            while True:
                l = p.stdout.readline().strip()
                if len(l) == 0:
                    break
                if self.kernel == 'any':
                    # firmware / udev
                    paths = ('/etc/udev/rules.d/', '/lib/firmware/', '/etc/',
                             '/usr/share/doc/')
                    if not True in map(lambda x: l.startswith(x), paths):
                        raise SystemExit, "Error: unsupported file %s in %s" % (l, self.fname)
                else:
                    # kernel modules
                    if not l.startswith('/lib/modules/'+self.kernel+'/extra/'):
                        raise SystemExit, "Error: unsupported file %s in %s" % (l, self.fname)
            p.wait()

    def toxml(self, doc):
        common_attrs = ('label', 'type', 'size', 'md5')

        pe = doc.createElement("package")
        for a in common_attrs:
            pe.setAttribute(a, self.__dict__[a])
        if self.type == 'driver-rpm':
            pe.setAttribute('kernel', self.kernel)
        pe.appendChild(doc.createTextNode(os.path.basename(self.fname)))

        return pe

    def flavour(self):
        if self.type == 'driver-rpm':
            m = re.search('([a-z]+)$', self.kernel)
            return m.group(1)
        else:
            return ''

    def __repr__(self):
        return str(self.__dict__)

requires_attrs = ('originator', 'name', 'test', 'product', 'version')

# dependency description
class Requires(dict):
    def __init__(self, *args, **attrs) :
        if False in map(lambda x: x in attrs, requires_attrs):
            raise SystemExit, "Missing mandatory attribute"
        valid = ('eq', 'ne', 'lt', 'gt', 'le', 'ge')
        if attrs['test'] not in valid:
            raise SystemExit, "Invalid test attribute"
        dict.__init__(self, *args, **attrs) 

# standard dependencies
try:
    from xcp.branding import *
except:
    pass
try:
    xcp = Requires(originator='xcp', name='main', test='eq', product=PLATFORM_NAME,
                   version=PLATFORM_VERSION)
except:
    pass
try:
    xs = Requires(originator='xs', name='main', test='eq', product=PRODUCT_BRAND,
                  version=PRODUCT_VERSION)
except:
    pass

# re-order packages according to internal dependencies
def _order_pkgs(pkgs):
    legacy_pkgs = filter(lambda x: not x.type.endswith('rpm'), pkgs)
    rpm_pkgs = filter(lambda x: x.type.endswith('rpm'), pkgs)

    tlate = dict(zip(map(lambda x:
                         subprocess.Popen(['rpm', '--nosignature', '-q', '--qf',
                                           '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}',
                                           '-p', x.fname], stdout=subprocess.PIPE).
                         communicate()[0], rpm_pkgs), rpm_pkgs))

    ordered = []
    p = subprocess.Popen(['rpm', '--nosignature', '-ivv', '--test'] +
                         map(lambda x: x.fname, rpm_pkgs),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, out = p.communicate()

    parse = False
    for line in out.split('\n'):
        if line.startswith('D: closed'):
            parse = False
        if 'tsorting packages' in line:
            parse = True
        elif parse:
            if not line.startswith('D: =='):
                a = line.split()
                if len(a) == 8:
                    ordered.append(a[7][1:])
                else:
                    parse = False

    return legacy_pkgs + map(lambda x: tlate[x], ordered)

def install_sh_text():
    return """#!/bin/sh
exec ${0%.sh} $*
"""

setup_attrs = ('originator', 'name', 'product', 'version')
opt_attrs = ('build', 'memory_requirement_mb', 'enforce_homogeneity')
setup_args = ('vendor', 'description')

# main pack builder
def setup(**attrs):
    if False in map(lambda x: x in attrs and attrs[x] != None, setup_attrs):
        raise SystemExit, "Error: missing mandatory attribute"
    if False in map(lambda x: x in attrs and attrs[x] != None, setup_args):
        raise SystemExit, "Error: missing mandatory argument"

    if ' ' in attrs['originator']:
        raise SystemExit, "Error: invalid originator"
    if ' ' in attrs['name']:
        raise SystemExit, "Error: invalid name"

    if 'enforce_homogeneity' in attrs:
        if attrs['enforce_homogeneity']:
            attrs['enforce_homogeneity'] = 'true'
        else:
            del attrs['enforce_homogeneity']
    if 'memory_requirement_mb' in attrs:
        attrs['memory_requirement_mb'] = str(attrs['memory_requirement_mb'])

    if 'output' not in attrs:
        attrs['output'] = ['iso']

    pkgs = []
    if 'packages' in attrs:
        pkgs = map(lambda x: Package(x), attrs['packages'])

    if 'outdir' not in attrs:
        parser = OptionParser()
	parser.add_option('-o', '--output', dest="outdir",
			  help="directory to output to", metavar="dir")
	
	(options, args) = parser.parse_args()

	if not options.outdir:
	    parser.error("Missing output directory")
	attrs['outdir'] = options.outdir

	if len(args) > 0:
	    pkgs += map(lambda x: Package(x), args)

    if 'reorder' in attrs and attrs['reorder']:
        pkgs = _order_pkgs(pkgs)
    if 'permit_legacy' in attrs and attrs['permit_legacy']:
	Package.permit_legacy = True
    
    # Check packages
    for pkg in pkgs:
        pkg.check()
    xen_pkgs = set(map(lambda y: y.label+':'+y.kernel.replace('xen', ''),
                       filter(lambda x: x.flavour() == 'xen', pkgs)))
    kdump_pkgs = set(map(lambda y: y.label+':'+y.kernel.replace('kdump', ''),
                         filter(lambda x: x.flavour() == 'kdump', pkgs)))
    if len(xen_pkgs.difference(kdump_pkgs)) > 0:
        raise SystemExit, "Error: no kdump kernel module found for " + \
              ','.join(xen_pkgs.difference(kdump_pkgs))
    if len(kdump_pkgs.difference(xen_pkgs)) > 0:
        raise SystemExit, "Error: no xen kernel module found for " + \
              ','.join(kdump_pkgs.difference(xen_pkgs))

    # Create metadata
    dom = xml.dom.minidom.getDOMImplementation()

    rdoc = dom.createDocument(None, "repository", None)
    rtop = rdoc.documentElement
    for a in setup_attrs:
        rtop.setAttribute(a, attrs[a])
    for a in opt_attrs:
        if a in attrs:
            rtop.setAttribute(a.replace('_', '-'), attrs[a])
    te = rdoc.createElement("description")
    te.appendChild(rdoc.createTextNode(attrs['description']))
    rtop.appendChild(te)

    if 'requires' in attrs:
        for r in attrs['requires']:
            re = rdoc.createElement("requires")
            for a in requires_attrs:
                re.setAttribute(a, r[a])
            rtop.appendChild(re)

    pdoc = dom.createDocument(None, "packages", None)
    ptop = pdoc.documentElement
    for pkg in pkgs:
        pe = pkg.toxml(pdoc)
        ptop.appendChild(pe)

    # Create outputs
    if 'dir' in attrs['output']:
        fh = open(os.path.join(attrs['outdir'], "XS-REPOSITORY"), 'w')
        fh.write(rtop.toprettyxml())
        fh.close()

        fh = open(os.path.join(attrs['outdir'], "XS-PACKAGES"), 'w')
        fh.write(ptop.toprettyxml())
        fh.close()

        for pkg in pkgs:
            shutil.copy(pkg.fname, attrs['outdir'])

    tmpdir = None
    if True in map(lambda x: x in attrs['output'], ('iso', 'tar')):
        tmpdir = tempfile.mkdtemp(prefix = 'pack-')
        bindir = os.path.dirname(sys.argv[0])
        if os.path.exists(os.path.join(bindir, "suppack-install.py")):
            scriptdir = bindir
	elif os.path.exists("/usr/bin/suppack-install.py"):
	    scriptdir = "/usr/bin"
	else:
            raise SystemExit, "Cannot locate suppack-install.py"

        fh = open(os.path.join(tmpdir, "XS-REPOSITORY"), 'w')
        fh.write(rtop.toprettyxml())
        fh.close()

        fh = open(os.path.join(tmpdir, "XS-PACKAGES"), 'w')
        fh.write(ptop.toprettyxml())
        fh.close()

        for pkg in pkgs:
            os.symlink(os.path.abspath(pkg.fname),
                       os.path.join(tmpdir, os.path.basename(pkg.fname)))

        # Copy install scripts
        fh = open(os.path.join(tmpdir, "install.sh"), 'w')
        fh.write(install_sh_text())
        fh.close()
        os.chmod(os.path.join(tmpdir, "install.sh"),
                 stat.S_IRUSR|stat.S_IWUSR|stat.S_IXUSR|stat.S_IRGRP|stat.S_IROTH)

        shutil.copy(os.path.join(scriptdir, "suppack-install.py"),
                    os.path.join(tmpdir, "install"))

    if 'tar' in attrs['output']:
        tf = tarfile.TarFile(os.path.join(attrs['outdir'], attrs['name']+'.tar.gz'), 'w')

        for fname in os.listdir(tmpdir):
            s = os.stat(os.path.join(tmpdir, fname))
            ti = tarfile.TarInfo(fname)
            ti.uname = 'root'
            ti.gname = 'root'
            ti.mode = s.st_mode
            ti.size = s.st_size
            ti.mtime = s.st_mtime
            fh = open(os.path.join(tmpdir, fname))
            tf.addfile(ti, fh)
            fh.close()

        tf.close()

    if 'iso' in attrs['output']:
        subprocess.call(['mkisofs', '-f', '-A', attrs['vendor'], '-V',
                         attrs['description'], '-J', '-joliet-long',
                         '-r', '-o', os.path.join(attrs['outdir'], attrs['name']+'.iso'),
                         tmpdir])

    if tmpdir:
        shutil.rmtree(tmpdir, True)
