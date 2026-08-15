#-------------------------------------------------------------------------------
# Name:        web_interface
# Purpose:     Entry point script for the navigation_server web interface
#
# Author:      Vibe Code
#
# Created:     15/08/2025
# Copyright:   (c) Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------
import sys
import re

from navigation_server.web_server import web_main

if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script\.pyw|\.exe)?$', '', sys.argv[0])
    sys.exit(web_main())
