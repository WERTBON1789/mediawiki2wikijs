#!/usr/bin/env python3
import sys
import os
import datetime
from typing import Generator, List
import paramiko
from mediawiki_dump.dumps import LocalFileDump
from mediawiki_dump.reader import DumpReader
from mediawiki_dump.entry import DumpEntry

WIKIJS_HOST              = os.environ.get("WIKIJS_HOST")
WIKIJS_TOKEN             = os.environ.get("WIKIJS_TOKEN")
MEDIAWIKI_HOST           = os.environ.get("MEDIAWIKI_SSH_HOST")
MEDIAWIKI_SSH_PORT       = os.environ.get("MEDIAWIKI_SSH_PORT")
MEDIAWIKI_SSH_PASSWD     = os.environ.get("MEDIAWIKI_SSH_PASSWD")
MEDIAWIKI_SSH_USER       = os.environ.get("MEDIAWIKI_SSH_USER")

WIKI_XML_LOCATION        = "/home/jan/wiki.xml"

class MediawikiMigration:
    def __init__(self, hostname: str, ssh_user: str, ssh_passwd: str, ssh_port=22) -> None:
        self.hostname = hostname
        self.ssh_user = ssh_user
        self.ssh_passwd = ssh_passwd
        self.ssh_port = ssh_port
    
    def download_wiki_dump(self, localpath: str):
        ssh = paramiko.SSHClient()
        
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.hostname, self.ssh_port, self.ssh_user, self.ssh_passwd)
        sftp = ssh.open_sftp()
        
        stdin,stdout,stderr = ssh.exec_command("php /var/www/html/wiki/maintenance/dumpBackup.php --full > /tmp/dump.xml")
        stdin.close()
        
        stdout.channel.recv_exit_status()
        
        sftp.get("/tmp/dump.xml", localpath)
    
    def read_dump(self, dump_file: str, sort_pages: bool=False) -> List[DumpEntry]:
        dump = LocalFileDump(dump_file)
        pages: Generator[DumpEntry, None, None] = DumpReader().read(dump)
        if sort_pages:
            return sorted(pages, key=lambda x: x.timestamp)
        else:
            return list(pages)

def main():
    pass


if __name__ == '__main__':
    main()