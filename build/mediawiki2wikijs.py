#!/usr/bin/env python3
import sys
import os
import paramiko
from mediawiki_dump.dumps import LocalFileDump
from mediawiki_dump.reader import DumpReader

WIKIJS_HOST          = os.environ.get("WIKIJS_HOST")
WIKIJS_TOKEN         = os.environ.get("WIKIJS_TOKEN")
MEDIAWIKI_HOST       = os.environ.get("MEDIAWIKI_SSH_HOST")
MEDIAWIKI_SSH_PORT   = os.environ.get("MEDIAWIKI_SSH_PORT")
MEDIAWIKI_SSH_PASSWD = os.environ.get("MEDIAWIKI_SSH_PASSWD")
MEDIAWIKI_SSH_USER   = os.environ.get("MEDIAWIKI_SSH_USER")


def main():
    pass

if __name__ == '__main__':
    main()