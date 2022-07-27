#!/usr/bin/env python3
from dataclasses import astuple, dataclass
import re
import sys
import os
import datetime
import paramiko
from subprocess import PIPE, Popen, call
from typing import Generator, List
from mediawiki_dump.dumps import LocalFileDump
from mediawiki_dump.reader import DumpReader
from mediawiki_dump.entry import DumpEntry
from wikijspy import *

WIKIJS_HOST              = os.environ.get("WIKIJS_HOST")
WIKIJS_TOKEN             = os.environ.get("WIKIJS_TOKEN")
MEDIAWIKI_HOST           = os.environ.get("MEDIAWIKI_SSH_HOST")
MEDIAWIKI_SSH_PORT       = os.environ.get("MEDIAWIKI_SSH_PORT")
MEDIAWIKI_SSH_PASSWD     = os.environ.get("MEDIAWIKI_SSH_PASSWD")
MEDIAWIKI_SSH_USER       = os.environ.get("MEDIAWIKI_SSH_USER")

WIKI_XML_LOCATION        = "/data/wiki.xml"
WIKI_MD_DIR              = "/data/wiki-md"
WIKI_TXT_DIR             = "/data/wiki-txt"

@dataclass
class PageMetaData:
    content: str
    contributor: str
    timestamp: str
    md_content: str = None
    
    def __iter__(self) -> tuple:
        return iter(astuple(self))

class PageCollection:
    def __init__(self, title: str, creation_date: str) -> None:
        self.title: str = title
        self.creation_date: str = creation_date
        self.last_updated: str = ""
        self.metadata_list: List[PageMetaData] = []
        self.counter: int = 0
        
    def add_entry(self, content: str, contributor: str, timestamp: str):
        self.metadata_list.append(PageMetaData(content, contributor, timestamp))
        if self.last_updated < timestamp:
            self.last_updated = timestamp
        self.counter += 1
    
    def add_markdown_to_index(self, md_content: str, index: int):
        self[index].md_content = md_content
    
    def __iter__(self):
        self.i = 0
        self.max = len(self.metadata_list)-1
        return self
    
    def __next__(self):
        if self.i<=self.max:
            result = self.i
            self.i += 1
            return self.metadata_list[result]
        else:
            raise StopIteration
    
    def __getitem__(self, item: int):
        return self.metadata_list[item]

class MediawikiMigration:
    def __init__(self, mediawiki_host: str, ssh_user: str, ssh_passwd: str, wikijs_host: str, wikijs_token: str, ssh_port=22):
        self.mediawiki_host = mediawiki_host
        self.ssh_user = ssh_user
        self.ssh_passwd = ssh_passwd
        self.ssh_port = ssh_port
        self.wikijs_host = wikijs_host
        self.wikijs_token = wikijs_token
        self.pages_api = PagesApi(ApiClient(Configuration(WIKIJS_HOST, WIKIJS_TOKEN)))
    
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
    
    def migrate(self, pages: List[str]=None):
        page_dump = self.read_dump(WIKI_XML_LOCATION, sort_pages=True)
        
        page_data: Dict[str, PageCollection] = {}
        
        for page in page_dump:

            page_title = page.title.split(':')[-1]
                        
            page_path = page.title\
                .replace(':', '/')\
                .replace(' ', '_')\
                .replace('.', '_')
            
            if not page_path in page_data:
                page_data[page_path] = PageCollection(page_title, page.timestamp)
            page_data[page_path].add_entry(page.content, page.contributor, page.timestamp)
            
        
        for path,data in page_data.items():
            is_published = True
            is_private = False
            page_id = self.page_exists(path)
            if page_id != -1:
                self.pages_api.delete(DefaultResponseOutput({"responseResult": ["errorCode"]}), page_id)
                page_id = -1
            for entry in data:
                exitcode,stdout,stderr = self.convert_content(entry.content)
            
                if exitcode != 0:
                    patched_content = self.patch_broken_content(entry.content, stderr)
                    exitcode,stdout,stderr = self.convert_content(patched_content)
                    if exitcode != 0:
                        for i in range(5):
                            exitcode,stdout,stderr = self.convert_content(patched_content)
                            if exitcode == 0:
                                break
                
                if exitcode == 0:
                    markdown_content = self.fix_hyper_links(stdout.decode('utf-8'))
                    entry.md_content = markdown_content
                else:
                    continue
                if page_id != -1:
                    result = self.pages_api.update(PageResponseOutput({
                        "responseResult": ["succeeded","errorCode","message"]
                    }),
                        page_id,
                        content=entry.md_content,
                        isPublished=is_published,
                        isPrivate=is_private
                    )
                else:
                    result = self.pages_api.create(PageResponseOutput({
                        "responseResult": ["succeeded","errorCode","message"],
                        "page": ["id"]
                    }),
                        content=entry.md_content,
                        editor="markdown",
                        isPrivate=is_private,
                        isPublished=is_published,
                        locale="en",
                        path=path,
                        tags=[],
                        title=data.title,
                        description=""
                    )
                    page_id = result["pages"]["create"]["page"]["id"]

    
    def convert_content(self, content: str):
        p = Popen(args=['pandoc', '-f', 'mediawiki', '-t', 'gfm', '-o', '/dev/stdout', '--wrap=none'], stdin=PIPE, stdout=PIPE, stderr=PIPE)
        stdout,stderr = p.communicate(input=content.encode('utf-8'))
        
        exitcode = p.wait()
        return (exitcode, stdout, stderr)
        
    def fix_hyper_links(self, content: str):
        split_content = content.splitlines()
    
        for i in range(len(split_content)):
            regex = re.search("\[(.+)\]\(Media:(.+) \"wikilink\"\)", split_content[i])
            if regex != None:
                split_content[i] = re.sub("\[.+\]\(Media:.+ \"wikilink\"\)", f"[{regex.group(1)}](/assets/{regex.group(2).lower()} \"{regex.group(1)}\")", split_content[i])
            regex = re.search("\[(.+)\]\((.+) \"wikilink\"\)", split_content[i])
            if regex != None:
                split_content[i] = re.sub("\[.+\]\(.+ \"wikilink\"\)", f"[{regex.group(1).replace(':', '/')}](/{regex.group(2).replace(':', '/')} \"{regex.group(1).replace(':', '/')}\")", split_content[i])
            regex = re.search("<a href=\"(.+)\" title=\"(.+)\">(.+)</a>", split_content[i])
            if regex != None:
                split_content[i] = re.sub("<a href=\".+\" title=\".+\">.+</a>", f"<a href=\"/{regex.group(1).replace(':', '/')}\" title=\"{regex.group(3)}\">{regex.group(3)}</a>", split_content[i])
            regex = re.search("\!\[(.*)\]\((.+) \"(.+)\"\)", split_content[i])
            if regex != None:
                split_content[i] = re.sub("\!\[.*\]\(.+ \".+\"\)", f"![{regex.group(1)}](/assets/{regex.group(2).lower()} \"{regex.group(3)}\")", split_content[i])
            regex = re.search("<img src=\"(.+)\" title=\"(.+)\" alt=\"(.+)\" />", split_content[i])
            if regex != None:
                split_content[i] = re.sub("<img src=\".+\" title=\".+\" alt=\".+\" />", f"<img src=\"/assets/{regex.group(1).lower()}\" title=\"{regex.group(2)}\" alt=\"{regex.group(3)}\" />", split_content[i])
            
        content = '\n'.join(split_content)

        return content
    
    def patch_broken_content(self, content: str, stderr: bytes):
        stderr = stderr.decode("utf-8")
        
        content = re.sub("{{prettytable}} width=.+%", "{{prettytable}}", content)
        
        split_content = content.splitlines()
        replace = False
        for i in range(len(split_content)):
            if split_content[i].find("{|") != -1:
                replace = True
            elif split_content[i].find("|}") != -1:
                replace = False
            
            if replace:
                if split_content[i].find("|}") == -1 and split_content[i].find("{|") == -1 and split_content[i].find("!") == -1:
                    split_content[i] = split_content[i].replace("|", "!", 1)
        
        if "unexpected end of input" in stderr:
            regex = re.search("(?s)<pre>(?!.+</pre>)", content)
            if regex != None:
                split_content.append("\n</pre>")
            else:
                regex = re.search("(?s)\{\|(?!.+\|\})", content)
                if regex != None:
                    split_content.append("\n|}")
        
        if 'unexpected "="' in stderr:
            regex = re.search("line (.+),", stderr)
            if regex != None:
                num = int(regex.group(1))-1
                del split_content[num]
                
        if "unexpected \"}\"" in stderr:
            regex = re.search("line (.+),", stderr)
            if regex != None:
                num = int(regex.group(1))-1
                split_content[num] = split_content[num].replace("}", "|}")
        
        content = '\n'.join(split_content)
        
        return content
    
    def page_exists(self, path: str) -> int:
        path_id_list = self.pages_api.list(PageListItemOutput(["id", "path"]))["pages"]["list"]
        id_list = [id for id,page_path in [(item["id"], item["path"]) for item in path_id_list] if page_path == path]
        if len(id_list) > 0:
            return id_list[0]
        else:
            return -1

def main():
    migration = MediawikiMigration(MEDIAWIKI_HOST, MEDIAWIKI_SSH_USER, MEDIAWIKI_SSH_PASSWD, WIKIJS_HOST, WIKIJS_TOKEN, MEDIAWIKI_SSH_PORT)
    migration.migrate()

if __name__ == '__main__':
    main()