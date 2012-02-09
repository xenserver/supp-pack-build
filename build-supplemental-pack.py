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

"""compatibility script to build XCP supplemental packs"""

from optparse import OptionParser

import sys

from xcp.supplementalpack import *

if __name__ == '__main__':
    parser = OptionParser()
    parser.set_defaults(homogeneous=False, iso=True, tar=False, reorder=True, xcp=False)
    parser.add_option('--output', dest="outdir",
                      help="directory to output to", metavar="dir")
    parser.add_option('--vendor-code', dest="originator",
                      help="vendor identifier", metavar="vc")
    parser.add_option('--vendor-name', dest="vendor",
                      help="vendor name", metavar="vn")
    parser.add_option('--label', dest="name",
                      help="package label", metavar="label")
    parser.add_option('--text', dest="description",
                      help="package description", metavar="text")
    parser.add_option('--version', dest="version",
                      help="package version", metavar="ver")
    parser.add_option('--build', dest="build",
                      help="package build", metavar="build")
    parser.add_option('--repo-data', action="store_true", dest="repo_data")
    parser.add_option('--mem', type="int", dest="memory_requirement_mb",
                      help="memory overhead", metavar="mem")
    parser.add_option('--homogeneous', action="store_true", dest="enforce_homogeneity",
                      help="enforce pool-wide presence")
    parser.add_option('--no-iso', action="store_false", dest="iso",
                      help="do not create ISO")
    parser.add_option('--tarball', action="store_true", dest="tar",
                      help="create tarball")
    parser.add_option('--reorder', action="store_true", dest="reorder",
                      help="Re-order packages in dependency order")
    parser.add_option('--noreorder', action="store_false", dest="reorder")
    parser.add_option('--xcp', action="store_true", dest="xcp")

    (options, args) = parser.parse_args()

    mandatory_opts = ("outdir", "originator", "vendor", "name", "description",
                      "version")

    params = options.__dict__

    if False in map(lambda x: x in params, mandatory_opts):
        parser.print_usage()
        sys.exit(1)

    if options.repo_data:
        raise SystemExit, "Arbitary metadata no longer supported"

    outputs = []
    if options.iso:
        outputs.append('iso')
    if options.tar:
        outputs.append('tar')
    params['output'] = outputs

    if options.xcp:
        params['requires'] = [xcp]
	params['product'] = 'XCP'
    else:
        params['requires'] = [xs]
	params['product'] = 'XenServer'

    params['packages'] = args

    setup(**params)
