#!python
import sys
import re
import navigation_server

if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script\.pyw|\.exe)?$', '', sys.argv[0])
    sys.exit(navigation_server.server_main())