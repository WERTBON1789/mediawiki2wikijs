#!/usr/bin/env python3
import json
import sys
import os
import re
import paramiko
import logging
import psycopg as psql
import ldap3
import requests
from dataclasses import astuple, dataclass
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
PSQL_HOST                = os.environ.get("PSQL_HOST")
PSQL_PORT                = os.environ.get("PSQL_PORT")
LDAP_HOST                = os.environ.get("LDAP_HOST")
LDAP_ADMIN_DN            = os.environ.get("LDAP_ADMIN_DN")
LDAP_ADMIN_PASSWD        = os.environ.get("LDAP_ADMIN_PASSWD")
LDAP_USERS_DN            = os.environ.get("LDAP_USERS_DN")
LDAP_FILTER              = os.environ.get("LDAP_FILTER")
IMPORT_LDAP              = os.environ.get("IMPORT_LDAP")
MEDIAWIKI_ASSETS         = os.environ.get("MEDIAWIKI_ASSETS")

WIKI_XML_LOCATION        = "/data/wiki.xml"
WIKI_MD_DIR              = "/data/wiki-md"
WIKI_TXT_DIR             = "/data/wiki-txt"
MIGRATION_LOG            = "/data/wiki-migration.log"
ERR_PAGES_LOG            = "/data/err-pages.log"
WIKI_IMG_LOCATION        = "/data/wiki-img.tar.gz"
ASSET_FOLDER             = "assets"

logger = logging.getLogger(__name__)
logging.basicConfig(filename=MIGRATION_LOG, level=logging.INFO, filemode='a')
logging.getLogger("gql").setLevel(logging.WARNING)

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

    def __setitem__(self, index: int, value):
        self.metadata_list[index] = value


class AuthenticationUserErrors(Enum):
    Nothing = 0
    AuthGenericError = 1001
    AuthLoginFailed = 1002
    AuthProviderInvalid = 1003
    AuthAccountAlreadyExists = 1004
    AuthTFAFailed = 1005
    AuthTFAInvalid = 1006
    BruteInstanceIsInvalid = 1007
    BruteTooManyAttempts = 1008
    UserCreationFailed = 1009
    AuthRegistrationDisabled = 1010
    AuthRegistrationDomainUnauthorized = 1011
    InputInvalid = 1012
    AuthAccountBanned = 1013
    AuthAccountNotVerified = 1014
    AuthValidationTokenInvalid = 1015
    UserNotFound = 1016
    UserDeleteForeignConstraint = 1017
    UserDeleteProtected = 1018
    AuthRequired = 1019
    AuthPasswordInvalid = 1020

class MediawikiMigration:
    def __init__(self, mediawiki_host: str, ssh_user: str, ssh_passwd: str, wikijs_host: str, wikijs_token: str, ssh_port=22):
        self.mediawiki_host = mediawiki_host
        self.ssh_user = ssh_user
        self.ssh_passwd = ssh_passwd
        self.ssh_port = ssh_port
        self.wikijs_host = wikijs_host
        self.wikijs_token = wikijs_token
        self._api_client = ApiClient(Configuration(WIKIJS_HOST, WIKIJS_TOKEN))
        self.pages_api = PagesApi(self._api_client)
        self.auth_client = AuthenticationApi(self._api_client)
        self.users_client = UsersApi(self._api_client)
        self.assets_client = AssetsApi(self._api_client)
        self.sql_client = psql.connect(conninfo=f"host={WIKIJS_HOST.split('://')[-1]} port=5432 dbname=wiki user=wikijs password=1234 connect_timeout=10")
        self.page_dump: List[DumpEntry] = None
    
    def download_wiki_dump(self, localpath: str):
        ssh = paramiko.SSHClient()
        
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.mediawiki_host, self.ssh_port, self.ssh_user, self.ssh_passwd)
        sftp = ssh.open_sftp()
        
        stdin,stdout,stderr = ssh.exec_command("php /var/www/html/wiki/maintenance/dumpBackup.php --full > /tmp/dump.xml")
        stdin.close()
        
        stdout.channel.recv_exit_status()
        
        sftp.get("/tmp/dump.xml", localpath)
    
    def read_dump(self, dump_file: str, sort_pages: bool=False) -> List[DumpEntry]:
        if not self.page_dump is None:
            return self.page_dump
        dump = LocalFileDump(dump_file)
        pages: Generator[DumpEntry, None, None] = DumpReader().read(dump)
        if sort_pages:
            self.page_dump = sorted(pages, key=lambda x: x.timestamp)
            return self.page_dump
        else:
            self.page_dump = list(pages)
            return self.page_dump
    
    def download_wiki_images(self, localpath: str):
        ssh = paramiko.SSHClient()
        
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.mediawiki_host, self.ssh_port, self.ssh_user, self.ssh_passwd)
        sftp = ssh.open_sftp()
        
        stdin,stdout,stderr = ssh.exec_command(command=f"cd {MEDIAWIKI_ASSETS} ; tar -czf /tmp/wiki_images.tar.gz ./*")
        stdin.close()
        
        stdout.channel.recv_exit_status()
        
        sftp.get("/tmp/wiki_images.tar.gz", localpath)
    
    def unpack_wiki_images(self, localpath: str):
        if not os.path.exists("/tmp/assets"):
            os.mkdir("/tmp/assets")
            call(args=["tar", "-xf", f"{localpath}", "-C", "/tmp/assets"])
            
    def migrate_assets(self):
        file_ext_dict = {
            ".png" : "image/png",
            ".jpg" : "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif" : "image/gif",
            ".pdf" : "application/pdf",
            ".log" : "text/x-log",
            ".bin" : "application/octet-stream",
            ".txt" : "text/plain",
            ".zip" : "application/zip",
            ".diff": "text/x-patch",
            ".ico" : "image/x-icon"
        }
        
        url = f'{WIKIJS_HOST}/u'
        
        headers = {
            'Authorization': f'Bearer {WIKIJS_TOKEN}'
        }
        
        asset_folder_id = None
        
        self.download_wiki_images(WIKI_IMG_LOCATION)
        self.unpack_wiki_images(WIKI_IMG_LOCATION)
        
        for folder in self.assets_client.folders(AssetFolderOutput(["id", "slug"]), 0)["assets"]["folders"]:
            if folder["slug"] == ASSET_FOLDER:
                asset_folder_id = folder["id"]
        
        if asset_folder_id is None:
            self.assets_client.createFolder(DefaultResponseOutput({"responseResult": ["errorCode"]}), 0, "assets", "Assets")
        
        for folder in self.assets_client.folders(AssetFolderOutput(["id", "slug"]), 0)["assets"]["folders"]:
            if folder["slug"] == ASSET_FOLDER:
                asset_folder_id = folder["id"]
        
        self._api_client.send_request("mutation{site{updateConfig(uploadMaxFileSize:104857600){responseResult{errorCode}}}}") # Setting the file upload size limit to 100 mb
        
        for base,dirs,files in os.walk("/tmp/assets"):
            if files:
                if base.find("deleted") == -1 and base.find("archive") == -1:
                    for filename in files:
                        filepath = base+"/"+filename
                        with open(filepath, 'rb') as f:
                            
                            files = (
                                ('mediaUpload', (None, '{"folderId":'f'{asset_folder_id}''}')),
                                ('mediaUpload', (os.path.basename(filepath), f, file_ext_dict.get(os.path.splitext(filepath)[1], 'text/plain')))
                            )

                            requests.post(url, headers=headers, files=files)
    
    def migrate(self, page_whitelist: List[str]=None, page_blacklist: List[str] = None):
        page_dump = self.read_dump(WIKI_XML_LOCATION, sort_pages=True)
        
        page_data: Dict[str, PageCollection] = {}
        
        with open("./username_mapping.json", "r") as f:
            newname_dict: Dict[str, Any] = json.loads(f.read())
        
        logger.info("Contructing the page_data dict")
        for page in page_dump:

            page_title = page.title.split(':')[-1]
                        
            page_path = page.title\
                .replace(':', '/')\
                .replace(' ', '_')\
                .replace('.', '_')
            
            if page_whitelist:
                if not page_path in page_whitelist:
                    continue
                
            if page_blacklist:
                if page_path in page_blacklist:
                    continue
            
            if not page_path in page_data:
                page_data[page_path] = PageCollection(page_title, page.timestamp)
            page_data[page_path].add_entry(page.content, newname_dict.get(page.contributor, page.contributor), page.timestamp)
        logger.info("Finished construction of the page_data dict")
        
        for path,data in page_data.items():
            is_published = True
            is_private = False
            page_id = self.page_exists(path)
            if page_id != -1:
                logger.warning(f"Page {path} already existed and will be overwritten!")
                self.pages_api.delete(DefaultResponseOutput({"responseResult": ["errorCode"]}), page_id)
                page_id = -1
            for index,entry in enumerate(data):
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
                    logger.error(f"Failed to convert {path} version {index}")
                    data[index] = None
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
                    logger.info(f"Updated {path} to version {index}.")
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
                    logger.info(f"Created {path}.")
            
            data = list(filter(None, data))
            
            logger.info(f"Changing dates of page {path}...")
            self.change_page_dates(page_id, data)
            logger.info(f"Finished changing dates of page {path}.")
            logger.info(f"Changing authors of page {path}...")
            self.change_page_authors(page_id, data)
            logger.info(f"Finished changing authors of page {path}.")
            

    
    def convert_content(self, content: str):
        p = Popen(args=['pandoc', '-f', 'mediawiki', '-t', 'gfm', '-o', '/dev/stdout', '--wrap=none'], stdin=PIPE, stdout=PIPE, stderr=PIPE)
        stdout,stderr = p.communicate(input=content.encode('utf-8'))
        
        exitcode = p.wait()
        if exitcode != 0:
            logger.warning(f"Pandoc exited with an exitcode of {exitcode}")
            logger.debug(f"Pandoc output: stdout:{stdout.decode('utf-8')}\n")
            logger.debug(f"Pandoc output: stderr:{stderr.decode('utf-8')}\n")
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
    
    def change_page_dates(self, page_id: int, collection: PageCollection):
        if page_id == -1:
            return
        with self.sql_client.cursor() as cur:
            rev_id_list: List[int] = [item[0] for item in sorted(cur.execute(f"SELECT id FROM \"pageHistory\" WHERE \"pageId\"={page_id}").fetchall(), key = lambda x: x[0])]

            for rev_id,entry in zip(rev_id_list, collection):
                cur.execute(f'UPDATE "pageHistory" SET "versionDate" = \'{entry.timestamp}\' WHERE id={rev_id}')
            
            cur.execute(f'UPDATE pages SET "createdAt" = \'{collection[0].timestamp}\', "updatedAt" = \'{collection[-1].timestamp}\' WHERE id={page_id}')
        self.sql_client.commit()
    
    def change_page_authors(self, page_id: int, collection: PageCollection):
        if page_id == -1:
            return
        
        user_id_dict = {}
        
        user_id_list = self.users_client.list(UserMinimalOutput(["id", "name"]))["users"]["list"]
        
        for user in user_id_list:
            if not user["name"] in user_id_dict:
                user_id_dict[user["name"]] = user["id"]
        
        with self.sql_client.cursor() as cur:
            rev_id_list: List[int] = [item[0] for item in sorted(cur.execute(f"SELECT id FROM \"pageHistory\" WHERE \"pageId\"={page_id}").fetchall(), key = lambda x: x[0])]
            
            for rev_id,entry in zip(rev_id_list, collection):
                cur.execute(f'UPDATE "pageHistory" SET "authorId" = \'{user_id_dict[entry.contributor]}\' WHERE id={rev_id}')
            
            cur.execute(f'UPDATE pages SET "creatorId" = \'{user_id_dict[collection[0].contributor]}\', "authorId" = \'{user_id_dict[collection[-1].contributor]}\' WHERE id={page_id}')
        self.sql_client.commit()
    
    def import_users_from_ldap(self):
        logger.warning("Importing all LDAP users...")
        ldap = ldap3.Server(LDAP_HOST)
        ldap_connection = ldap3.Connection(ldap, LDAP_ADMIN_DN, LDAP_ADMIN_PASSWD)
        ldap_connection.bind()
        
        ldap_connection.search(LDAP_USERS_DN, LDAP_FILTER, attributes=['cn', 'mail', 'userPassword'])
        
        strats = self._api_client.send_request("query{authentication{activeStrategies(enabledOnly: true){displayName,key,strategy{key}}}}")
        
        ldap_strat_key = None
        
        for strat in strats["authentication"]["activeStrategies"]:
            if strat["strategy"]["key"] == "ldap":
                logger.info(f"Using Strategy {strat['displayName']}")
                ldap_strat_key = strat["key"]
        
        if ldap_strat_key is None:
            logger.error("Couldn't find a valid Authentication Strategy!")
            return

        for entry in ldap_connection.entries:
            logger.info(f"Creating user {str(entry['cn'])}.")
            result = self.users_client.create(UserResponseOutput({"responseResult": ["errorCode", "message"]}), str(entry["mail"]), str(entry["cn"]), ldap_strat_key, str(entry["userPassword"]))
            error_code = result["users"]["create"]["responseResult"]["errorCode"]
            if AuthenticationUserErrors(error_code) == AuthenticationUserErrors.AuthAccountAlreadyExists:
                logger.warning(f"There already is an account using this email: {str(entry['mail'])}")
            if AuthenticationUserErrors(error_code) == AuthenticationUserErrors.InputInvalid:
                logger.warning(f"The email of the LDAP user {str(entry['cn'])} is invalid!")
    
    def import_users_from_wiki(self):
        page_dump = self.read_dump(WIKI_XML_LOCATION, sort_pages=True)
        
        newname_dict = None
        
        with open("./username_mapping.json", "r") as f:
            newname_dict: Dict[str, Any] = json.loads(f.read())
        
        wiki_users = []
        
        for page in page_dump:
            if not page.contributor in wiki_users:
                wiki_users.append(page.contributor)
        
        wikijs_users = [user["name"] for user in self.users_client.list(UserMinimalOutput(["id", "name"]))["users"]["list"]]
        
        for i in wiki_users:
            new_name = newname_dict.get(i, i)
            if new_name in wikijs_users:
                logger.warning(f"User {new_name} already exists on wikijs!")
            else:
                logger.info(f"Creating user {new_name}")
                result = self.users_client.create(UserResponseOutput({"responseResult": ["errorCode"], "user": ["id"]}), f"{new_name.lower().replace(' ', '_')}@example.com", new_name, "local", passwordRaw="65fb6d7e-3d77-44fe-97b7-45865d8acc56", mustChangePassword=True)
                error_code = result["users"]["create"]["responseResult"]["errorCode"]
                if AuthenticationUserErrors(error_code) == AuthenticationUserErrors.AuthAccountAlreadyExists:
                    logger.warning(f"There already is an account using this email: {new_name.lower().replace(' ', '_')}@example.com")
                    continue
                if AuthenticationUserErrors(error_code) == AuthenticationUserErrors.InputInvalid:
                    logger.warning(f"The email of the user {new_name} is invalid: {new_name.lower().replace(' ', '_')}@example.com")
                    continue
                
                for user in self.users_client.list(UserMinimalOutput(["id", "name"]))["users"]["list"]:
                    if new_name == user["name"]:
                        self.users_client.deactivate(DefaultResponseOutput({"responseResult": ["errorCode"]}), user["id"])

def main():
    migration = MediawikiMigration(MEDIAWIKI_HOST, MEDIAWIKI_SSH_USER, MEDIAWIKI_SSH_PASSWD, WIKIJS_HOST, WIKIJS_TOKEN, MEDIAWIKI_SSH_PORT)
    if IMPORT_LDAP == "true":
        migration.import_users_from_ldap()
    migration.import_users_from_wiki()
    if MEDIAWIKI_ASSETS:
        migration.migrate_assets()
    migration.migrate()
    

if __name__ == '__main__':
    main()
