#!/usr/bin/env python3
import json
import sys
import os
import re
from fnmatch import fnmatch
import ldap
import paramiko
import logging
import psycopg as psql
from dataclasses import astuple, dataclass
from subprocess import PIPE, Popen, call
from typing import Generator, List
from mediawiki_dump.dumps import LocalFileDump
from mediawiki_dump.reader import DumpReader
from mediawiki_dump.entry import DumpEntry
from typing import Any, Dict
from gql import Client, gql
from gql.dsl import DSLQuery, DSLMutation, DSLSchema, dsl_gql
from gql.transport.requests import RequestsHTTPTransport
import requests
from constants import *
from query_defs import *
from fix_links import fix_hyper_links
import pickle

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    handlers=[
                        logging.FileHandler(MIGRATION_LOG),
                        logging.StreamHandler(sys.stdout)
                    ])
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

    def add_entry(self, content: str, contributor: str, timestamp: str):
        self.metadata_list.append(PageMetaData(content, contributor,
                                               timestamp))
        if self.last_updated < timestamp:
            self.last_updated = timestamp

    def add_markdown_to_index(self, md_content: str, index: int):
        self[index].md_content = md_content

    def __iter__(self):
        self.i = 0
        self.max = len(self.metadata_list) - 1
        return self

    def __next__(self):
        if self.i <= self.max:
            result = self.i
            self.i += 1
            return self.metadata_list[result]
        else:
            raise StopIteration

    def __getitem__(self, item: int):
        return self.metadata_list[item]

    def __setitem__(self, index: int, value):
        self.metadata_list[index] = value

    def __bool__(self):
        return bool(self.metadata_list)


class MediawikiMigration:

    def __init__(self,
                 mediawiki_host: str,
                 ssh_user: str,
                 ssh_passwd: str,
                 wikijs_host: str,
                 wikijs_token: str,
                 ssh_port=22):
        self.mediawiki_host = mediawiki_host
        self.ssh_user = ssh_user
        self.ssh_passwd = ssh_passwd
        self.ssh_port = ssh_port
        self.wikijs_host = wikijs_host
        self.wikijs_token = wikijs_token
        client = Client(
            transport=RequestsHTTPTransport(
                url=WIKIJS_HOST + '/graphql',
                headers={'Authorization': 'Bearer ' + WIKIJS_TOKEN}),
            fetch_schema_from_transport=True,
        )
        self._session = client.connect_sync()
        self._dslschema = DSLSchema(client.schema)
        self.sql_client = psql.connect(
            conninfo=
            f"host={WIKIJS_HOST.split('://')[-1]} port=5432 dbname=wiki user=wikijs password=1234 connect_timeout=10"
        )
        self.page_dump: List[DumpEntry] = None

    def download_wiki_dump(self, localpath: str):
        ssh = paramiko.SSHClient()

        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.mediawiki_host, self.ssh_port, self.ssh_user,
                    self.ssh_passwd)
        sftp = ssh.open_sftp()

        stdin, stdout, _ = ssh.exec_command(
            "php /var/www/html/wiki/maintenance/dumpBackup.php --full > /tmp/dump.xml"
        )
        stdin.close()

        stdout.channel.recv_exit_status()

        sftp.get("/tmp/dump.xml", localpath)

    def read_dump(self,
                  dump_file: str,
                  sort_pages: bool = False) -> List[DumpEntry]:
        if not self.page_dump is None:
            return self.page_dump
        if os.path.exists(DUMP_OBJ):
            logger.info('Pickled object is present. loading page dump...')
            with open(DUMP_OBJ, 'rb') as f:
                self.page_dump = pickle.load(f)
                return self.page_dump
        dump = LocalFileDump(dump_file)
        pages: Generator[DumpEntry, None, None] = DumpReader().read(dump)
        if sort_pages:
            self.page_dump = sorted(pages, key=lambda x: x.timestamp)
            with open(DUMP_OBJ, 'wb') as f:
                pickle.dump(self.page_dump, f, pickle.HIGHEST_PROTOCOL)
            return self.page_dump
        else:
            self.page_dump = list(pages)
            with open(DUMP_OBJ, 'wb') as f:
                pickle.dump(self.page_dump, f, pickle.HIGHEST_PROTOCOL)
            return self.page_dump

    def download_wiki_images(self, localpath: str):
        ssh = paramiko.SSHClient()

        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.mediawiki_host, self.ssh_port, self.ssh_user,
                    self.ssh_passwd)
        sftp = ssh.open_sftp()

        stdin, stdout, _ = ssh.exec_command(
            command=
            f"cd {MEDIAWIKI_ASSETS} ; tar -czf /tmp/wiki_images.tar.gz ./*")
        stdin.close()

        stdout.channel.recv_exit_status()

        sftp.get("/tmp/wiki_images.tar.gz", localpath)

    def unpack_wiki_images(self, localpath: str):
        if not os.path.exists("/tmp/assets"):
            os.mkdir("/tmp/assets")
            call(args=["tar", "-xf", f"{localpath}", "-C", "/tmp/assets"])

    def migrate_assets(self):

        url = f'{WIKIJS_HOST}/u'

        headers = {'Authorization': f'Bearer {WIKIJS_TOKEN}'}

        file_ext_dict = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.pdf': 'application/pdf',
            '.log': 'text/x-log',
            '.bin': 'application/octet-stream',
            '.txt': 'text/plain',
            '.zip': 'application/zip',
            '.diff': 'text/x-patch',
            '.ico': 'image/x-icon'
        }

        asset_folder_id = None

        if not os.path.exists(WIKI_IMG_LOCATION):
            self.download_wiki_images(WIKI_IMG_LOCATION)
        self.unpack_wiki_images(WIKI_IMG_LOCATION)

        for folder in self._session.execute(
                gql('query{assets{folders(parentFolderId:0){id,slug}}}')
        )["assets"]["folders"]:
            if folder["slug"] == ASSET_FOLDER:
                asset_folder_id = folder["id"]

        if asset_folder_id is None:
            self._session.execute(
                dsl_gql(
                    DSLMutation(
                        self._dslschema.Mutation.assets.select(
                            self._dslschema.AssetMutation.createFolder(
                                parentFolderId=0,
                                slug=ASSET_FOLDER,
                                name=ASSET_FOLDER).select(
                                    self._dslschema.DefaultResponse.
                                    responseResult.select(
                                        self._dslschema.ResponseStatus.
                                        errorCode))))))

        for folder in self._session.execute(
                gql('query{assets{folders(parentFolderId:0){id,slug}}}')
        )["assets"]["folders"]:
            if folder["slug"] == ASSET_FOLDER:
                asset_folder_id = folder["id"]

        self._session.execute(
            gql("mutation{site{updateConfig(uploadMaxFileSize:104857600){responseResult{errorCode}}}}"
                ))  # Setting the file upload size limit to 100 mb

        present_files = [
            filename['filename'] for filename in self._session.execute(
                gql('query{assets{list(folderId: 1, kind: ALL){filename}}}'))
            ['assets']['list']
        ]

        for base, _, files in os.walk("/tmp/assets"):
            if files:
                if base.find("deleted") == -1 and base.find("archive") == -1:
                    for filename in files:
                        if filename.lower() in present_files:
                            logger.info(f'File {filename} already present.')
                            continue
                        filepath = base + "/" + filename
                        with open(filepath, 'rb') as f:
                            files = (('mediaUpload',
                                      (None,
                                       '{"folderId": %i}' % asset_folder_id)),
                                     ('mediaUpload',
                                      (filename, f.read(),
                                       file_ext_dict.get(
                                           os.path.splitext(filename)[1],
                                           'text/plain'))))
                            logger.info(f'Uploading file {filename}...')
                            r = requests.post(url=url,
                                              headers=headers,
                                              files=files)
                            if r.status_code != 200:
                                logger.warning(f'Failed to upload {filepath}!')

    def migrate(self,
                page_whitelist: List[str] = [],
                page_blacklist: List[str] = []):
        page_dump = self.read_dump(WIKI_XML_LOCATION, sort_pages=True)

        page_data: Dict[str, PageCollection] = {}

        with open("./username_mapping.json", "r") as f:
            newname_dict: Dict[str, Any] = json.load(f)

        logger.info("Contructing the page_data dict")
        for page in page_dump:

            page_title = page.title.split(':')[-1]

            page_path = page.title\
                .replace(':', '/')\
                .replace(' ', '_')\
                .replace('.', '_')

            if page_whitelist:
                if not any(fnmatch(page_path, pat) for pat in page_whitelist):
                    continue

            if page_blacklist:
                if any(fnmatch(page_path, pat) for pat in page_blacklist):
                    continue

            if not page_path in page_data:
                page_data[page_path] = PageCollection(page_title,
                                                      page.timestamp)
            tmp = newname_dict.get(page.contributor, page.contributor)
            if type(tmp) == str:
                new_name = tmp
            else:
                new_name = tmp.get('name', page.contributor)

            page_data[page_path].add_entry(page.content, new_name,
                                           page.timestamp)
        logger.info("Finished construction of the page_data dict")

        for path, data in page_data.items():
            page_id = self.page_exists(path)
            if page_id != -1:
                logger.warning(
                    f"Page {path} already existed and will be overwritten!")
                self._session.execute(delete_page, {'id': page_id})
                page_id = -1
            for index, entry in enumerate(data):

                # Remove all pipe characters from external links
                split_content = entry.content.splitlines()
                for idx, line in enumerate(split_content):
                    split_content[idx] = re.sub(r'(?!.*(?<!\[)\[(?!\[).*)\s*\|\s*(?=.*(?<!\])\](?!\]))', ' ', line)
                entry.content = '\n'.join(split_content)

                exitcode, stdout, stderr = self.convert_content(entry.content)

                if exitcode != 0:
                    patched_content = self.patch_broken_content(
                        entry.content, stderr)
                    exitcode, stdout, stderr = self.convert_content(
                        patched_content)
                    if exitcode != 0:
                        for _ in range(5):
                            exitcode, stdout, stderr = self.convert_content(
                                patched_content)
                            if exitcode == 0:
                                break

                if exitcode != 0:
                    logger.error(f"Failed to convert {path} version {index}")
                    data[index] = None
                    continue

                entry.md_content = fix_hyper_links(stdout.decode('utf-8'))

                script = ''
                if entry.content.startswith('#REDIRECT') or entry.content.startswith('#WEITERLEITUNG'):
                    m = re.search(r'\[.+?\]\((.+?) .*\)', entry.md_content)
                    if m is not None:
                        script = '<script>window.location.href = "{}";</script>'.format(m[1])

                if page_id != -1:
                    self._session.execute(update_page, {
                        'id': page_id,
                        'content': entry.md_content,
                        'script': script,
                    })
                    logger.info(f"Updated {path} to version {index}.")
                else:
                    result = self._session.execute(
                        create_page, {
                            'content': entry.md_content,
                            'path': path,
                            'title': data.title,
                            'scriptJs': script,
                        })
                    try:
                        page_id = result["pages"]["create"]["page"]["id"]
                    except:
                        logger.error(result['pages']['create']
                                     ['responseResult']['slug'])
                    logger.info(f"Created {path}.")

            data = list(filter(None, data))
            page_data[path] = data

            if page_whitelist:
                logger.info(f"Rendering page {path}...")
                self._session.execute(
                    gql('mutation{pages{render(id: %i){responseResult{errorCode}}}}'
                        % page_id))
            logger.info(f"Changing dates of page {path}...")
            self.change_page_dates(page_id, data)
            logger.info(f"Finished changing dates of page {path}.")
            logger.info(f"Changing authors of page {path}...")
            self.change_page_authors(page_id, data)
            logger.info(f"Finished changing authors of page {path}.")

        page_data = {k: v for k, v in page_data.items() if v}

        path_id_dict = {}
        for item in self._session.execute(
                dsl_gql(
                    DSLQuery(
                        self._dslschema.Query.pages.select(
                            self._dslschema.PageQuery.list.select(
                                self._dslschema.PageListItem.id,
                                self._dslschema.PageListItem.path))))
        )['pages']['list']:
            path_id_dict[item["path"]] = item["id"]

        for path, data in page_data.items():
            if not page_whitelist:
                logger.info(f'Rerendering page {path}...')
                self._session.execute(
                    gql('mutation{pages{render(id: %i){responseResult{errorCode}}}}'
                        % path_id_dict[path]))
            logger.info(f"Updating last updated timestamp for page {path}...")
            self.change_latest_page_dates(path_id_dict[path], data)

    def convert_content(self, content: str):
        p = Popen(args=[
            'pandoc', '-f', 'mediawiki', '-t', 'gfm', '-o', '/dev/stdout',
            '--wrap=none'
        ],
                  stdin=PIPE,
                  stdout=PIPE,
                  stderr=PIPE)
        stdout, stderr = p.communicate(input=content.encode('utf-8'))

        exitcode = p.wait()
        if exitcode != 0:
            logger.warning(f"Pandoc exited with an exitcode of {exitcode}")
            logger.debug(f"Pandoc output: stdout:{stdout.decode('utf-8')}\n")
            logger.debug(f"Pandoc output: stderr:{stderr.decode('utf-8')}\n")
        return (exitcode, stdout, stderr)


    def patch_broken_content(self, content: str, stderr: bytes):
        stderr_str: str = stderr.decode("utf-8")

        content = re.sub("{{prettytable}} width=.+%", "{{prettytable}}",
                         content)

        split_content = content.splitlines()
        replace = False
        for i in range(len(split_content)):
            if split_content[i].find("{|") != -1:
                replace = True
            elif split_content[i].find("|}") != -1:
                replace = False

            if replace:
                if split_content[i].find("|}") == -1 and split_content[i].find(
                        "{|") == -1 and split_content[i].find("!") == -1:
                    split_content[i] = split_content[i].replace("|", "!", 1)

        if 'unexpected end of input' in stderr_str:
            regex = re.search("(?s)<pre>(?!.+</pre>)", content)
            if regex != None:
                split_content.append("\n</pre>")
            else:
                regex = re.search(r"(?s)\{\|(?!.+\|\})", content)
                if regex != None:
                    split_content.append("\n|}")

        if 'unexpected "="' in stderr_str:
            regex = re.search("line (.+),", stderr_str)
            if regex != None:
                num = int(regex.group(1)) - 1
                del split_content[num]

        if 'unexpected "}"' in stderr_str:
            regex = re.search("line (.+),", stderr_str)
            if regex != None:
                num = int(regex.group(1)) - 1
                split_content[num] = split_content[num].replace("}", "|}")

        content = '\n'.join(split_content)

        return content

    def page_exists(self, path: str) -> int:
        page_result = self._session.execute(
            search_page, {'path': path})['pages']['search']['results']

        for obj in page_result:
            id, l_path = obj.values()
            if l_path == path:
                return int(id)
        return -1

    def change_page_dates(self, page_id: int, collection: List[PageMetaData]):
        if page_id == -1:
            return
        with self.sql_client.cursor() as cur:
            rev_id_list: List[int] = [
                item[0] for item in sorted(cur.execute(
                    f"SELECT id FROM \"pageHistory\" WHERE \"pageId\"={page_id}"
                    .encode()).fetchall(),
                                           key=lambda x: x[0])
            ]

            for rev_id, entry in zip(rev_id_list, collection):
                cur.execute(
                    f'UPDATE "pageHistory" SET "versionDate" = \'{entry.timestamp}\' WHERE id={rev_id}'
                    .encode())

            cur.execute(
                f'UPDATE pages SET "createdAt" = \'{collection[0].timestamp}\' WHERE id={page_id}'
                .encode())
        self.sql_client.commit()

    def change_latest_page_dates(self, page_id: int,
                                 collection: PageCollection):
        if page_id == -1:
            return
        with self.sql_client.cursor() as cur:
            cur.execute(
                f'UPDATE pages SET "updatedAt" = \'{collection[-1].timestamp}\' WHERE id={page_id}'
                .encode())

        self.sql_client.commit()

    def change_page_authors(self, page_id: int,
                            collection: List[PageMetaData]):
        if page_id == -1:
            return
        global user_id_dict

        if 'user_id_dict' not in globals():
            query = dsl_gql(
                DSLQuery(
                    self._dslschema.Query.users.select(
                        self._dslschema.UserQuery.list.select(
                            self._dslschema.UserMinimal.name,
                            self._dslschema.UserMinimal.id))))
            user_id_list = [
                user.values()
                for user in self._session.execute(query)["users"]["list"]
            ]

            user_id_dict = dict(user_id_list)

        with self.sql_client.cursor() as cur:
            rev_id_list: List[int] = [
                item[0] for item in sorted(cur.execute(
                    f"SELECT id FROM \"pageHistory\" WHERE \"pageId\"={page_id}"
                    .encode()).fetchall(),
                                           key=lambda x: x[0])
            ]

            for rev_id, entry in zip(rev_id_list, collection):
                cur.execute(
                    f'UPDATE "pageHistory" SET "authorId" = \'{user_id_dict[entry.contributor]}\' WHERE id={rev_id}'
                    .encode())

            cur.execute(
                f'UPDATE pages SET "creatorId" = \'{user_id_dict[collection[0].contributor]}\', "authorId" = \'{user_id_dict[collection[-1].contributor]}\' WHERE id={page_id}'
                .encode())
        self.sql_client.commit()

    def update_timezone_of_all_users(self, timezone: str = "America/New_York"):
        user_id_list = [
            user['id'] for user in self._session.execute(
                dsl_gql(
                    DSLQuery(
                        self._dslschema.Query.users.select(
                            self._dslschema.UserQuery.list.select(
                                self._dslschema.UserMinimal.id)))))['users']
            ['list']
        ]

        for id in user_id_list:
            query = dsl_gql(
                DSLMutation(
                    self._dslschema.Mutation.users.select(
                        self._dslschema.UserMutation.update(
                            id=id, timezone=timezone).select(
                                self._dslschema.DefaultResponse.responseResult.
                                select(self._dslschema.ResponseStatus.errorCode
                                       )))))
            self._session.execute(query)

    def import_users_from_wiki(self):
        page_dump = self.read_dump(WIKI_XML_LOCATION, sort_pages=True)

        with open("./username_mapping.json", "r") as f:
            newname_dict: Dict[str, Any] = json.load(f)

        wiki_users = set([page.contributor for page in page_dump])

        wikijs_users = [
            user["name"] for user in self._session.execute(
                dsl_gql(
                    DSLQuery(
                        self._dslschema.Query.users.select(
                            self._dslschema.UserQuery.list.select(
                                self._dslschema.UserMinimal.name)))))['users']
            ['list']
        ]

        for i in wiki_users:
            tmp = newname_dict.get(i, i)
            email = None
            if type(tmp) == str:
                new_name = tmp
            elif type(tmp) == dict:
                email = tmp.get('email')
                new_name = tmp.get('name', i)
            if new_name in wikijs_users:
                logger.warning(f"User {new_name} already exists on wikijs!")
            else:
                logger.info(f"Creating user {new_name}")
                result = self._session.execute(
                    create_user, {
                        'email':
                        f"{new_name.lower().replace(' ', '_')}@example.com"
                        if email is None else email,
                        'name':
                        new_name,
                        'providerKey':
                        "local"
                    })
                error_code = result["users"]["create"]["responseResult"][
                    "errorCode"]
                if error_code == 1004:  # AuthAccountAlreadyExists
                    logger.warning(
                        f"There already is an account using this email: {new_name.lower().replace(' ', '_')}@example.com"
                    )
                    continue
                if error_code == 1012:  # InputInvalid
                    logger.warning(
                        f"The email of the user {new_name} is invalid: {new_name.lower().replace(' ', '_')}@example.com"
                    )
                    continue
                user_id = self._session.execute(
                    gql('query{users{search(query: "%s"){id}}}' %
                        new_name))['users']['search'][-1]['id']
                query = dsl_gql(
                    DSLMutation(
                        self._dslschema.Mutation.users.select(
                            self._dslschema.UserMutation.deactivate(
                                id=user_id).select(
                                    self._dslschema.DefaultResponse.
                                    responseResult.select(
                                        self._dslschema.ResponseStatus.
                                        succeeded)))))
                self._session.execute(query)

    def import_ldap_users(self):
        ldap_server = ldap.initialize(LDAP_HOST)
        ldap_server.bind_s(LDAP_ADMIN_DN, LDAP_ADMIN_PASSWD)

        auth_strats = self._session.execute(
            dsl_gql(
                DSLQuery(
                    self._dslschema.Query.authentication.select(
                        self._dslschema.AuthenticationQuery.
                        activeStrategies(enabledOnly=True).select(
                            self._dslschema.AuthenticationActiveStrategy.
                            displayName,
                            self._dslschema.AuthenticationActiveStrategy.key,
                            self._dslschema.AuthenticationActiveStrategy.key,
                            self._dslschema.AuthenticationActiveStrategy.
                            strategy.select(
                                self._dslschema.AuthenticationStrategy.key)))))
        )["authentication"]["activeStrategies"]

        ldap_strat_key = None

        for strat in auth_strats:
            if strat['strategy']['key'] == 'ldap':
                logger.info(f'Using Strategy {strat["displayName"]}')
                ldap_strat_key = strat['key']

        if ldap_strat_key is None:
            logger.error("Couldn't find a valid Authentication Strategy!")
            return

        users = ldap_server.search_s(LDAP_USER_DN,
                                     ldap.SCOPE_ONELEVEL,
                                     LDAP_USER_FILTER,
                                     attrlist=['cn', 'mail', 'userPassword'])

        for _, data in users:
            logger.info(f'Creating user {data["cn"][0].decode()}.')
            result = self._session.execute(
                create_user, {
                    'email': data['mail'][0].decode(),
                    'name': data['cn'][0].decode(),
                    'providerKey': ldap_strat_key,
                    'passwordRaw': data['userPassword'][0].decode()
                })

            error_code = result["users"]["create"]["responseResult"][
                "errorCode"]
            if error_code == 1004:  # AuthAccountAlreadyExists
                logger.warning(
                    f"There already is an account using this email: {data['mail'][0].decode()}"
                )
            if error_code == 1012:  # InputInvalid
                logger.warning(
                    f"The email of the LDAP user {data['cn'][0].decode()} is invalid!"
                )

        for group in LDAP_USER_GROUPS.split(','):
            if not ldap_server.search_s(LDAP_GROUP_DN,
                                        ldap.SCOPE_ONELEVEL,
                                        LDAP_GROUP_FILTER % group,
                                        attrlist=['cn']):
                logger.warning(
                    f'Group {group} doesn\'t exist in LDAP and won\'t be created in wikijs!'
                )
                continue

            group_id = None
            tmp = list(
                filter(
                    lambda inner_group: inner_group['name'] == group,
                    self._session.execute(gql('query{groups{list{id,name}}}'))
                    ['groups']['list']))
            if len(tmp) == 1:
                logger.info(f'Group {group} already exists.')
                group_id = tmp[0]['id']
            elif len(tmp) > 1:
                logger.warning(
                    f'There are multiple groups with the name "{group}"!')
                continue
            elif len(tmp) < 1:
                logger.info(
                    f'There is no group named "{group}", will create it...')
                group_id = self._session.execute(
                    dsl_gql(
                        DSLMutation(
                            self._dslschema.Mutation.groups.select(
                                self._dslschema.GroupMutation.
                                create(name=group).select(
                                    self._dslschema.GroupResponse.
                                    responseResult.select(
                                        self._dslschema.ResponseStatus.
                                        errorCode),
                                    self._dslschema.GroupResponse.group.select(
                                        self._dslschema.Group.id)))))
                )['groups']['create']['group']['id']
                logger.info(f'Created group {group}.')
            self._session.execute(
                dsl_gql(
                    DSLMutation(
                        self._dslschema.Mutation.groups.select(
                            self._dslschema.GroupMutation.update(
                                id=group_id,
                                name=group,
                                redirectOnLogin=LDAP_USER_GROUP_REDIRECT_URI,
                                permissions=[
                                    'read:pages', 'read:assets',
                                    'read:comments', 'write:comments'
                                ],
                                pageRules=[{
                                    'deny': False,
                                    'id': 'Migration-User-Read',
                                    'locales': [],
                                    'match': 'START',
                                    'path': '',
                                    'roles': ['read:pages']
                                }]).select(
                                    self._dslschema.DefaultResponse.
                                    responseResult.select(
                                        self._dslschema.ResponseStatus.
                                        errorCode))))))

        if not ldap_server.search_s(LDAP_GROUP_DN,
                                    ldap.SCOPE_ONELEVEL,
                                    LDAP_GROUP_FILTER % LDAP_ADMIN_GROUP,
                                    attrlist=['cn']):
            logger.warning(
                f'Group {LDAP_ADMIN_GROUP} doesn\'t exist in LDAP and won\'t be created in wikijs!'
            )

        group_id = None
        tmp = list(
            filter(
                lambda group: group['name'] == LDAP_ADMIN_GROUP,
                self._session.execute(
                    gql('query{groups{list{id,name}}}'))['groups']['list']))

        if len(tmp) == 1:
            logger.info(f'Group {LDAP_ADMIN_GROUP} already exists.')
            group_id = tmp[0]['id']
        elif len(tmp) > 1:
            logger.warning(
                f'There are multiple groups with the name "{LDAP_ADMIN_GROUP}"!'
            )
            return
        elif len(tmp) < 1:
            logger.info(
                f'There is no group named "{LDAP_ADMIN_GROUP}", will create it...'
            )
            group_id = self._session.execute(
                dsl_gql(
                    DSLMutation(
                        self._dslschema.Mutation.groups.select(
                            self._dslschema.GroupMutation.
                            create(name=LDAP_ADMIN_GROUP).select(
                                self._dslschema.GroupResponse.responseResult.
                                select(
                                    self._dslschema.ResponseStatus.errorCode),
                                self._dslschema.GroupResponse.group.select(
                                    self._dslschema.Group.id)))))
            )['groups']['create']['group']['id']
            logger.info(f'Created group {LDAP_ADMIN_GROUP}.')
        self._session.execute(
            dsl_gql(
                DSLMutation(
                    self._dslschema.Mutation.groups.select(
                        self._dslschema.GroupMutation.update(
                            id=group_id,
                            name=LDAP_ADMIN_GROUP,
                            redirectOnLogin=LDAP_USER_GROUP_REDIRECT_URI,
                            permissions=['manage:system'],
                            pageRules=[]).select(
                                self._dslschema.DefaultResponse.responseResult.
                                select(self._dslschema.ResponseStatus.errorCode
                                       ))))))

    def set_defaults(self):
        if LOCALE != 'en':
            logger.info(f'Downloading locale {LOCALE}.')
            self._session.execute(
                gql('mutation{localization{downloadLocale(locale: "%s"){responseResult{succeeded}}}}'
                    % LOCALE))
            logger.info(f'Setting locale to {LOCALE}.')
            self._session.execute(
                gql('mutation{localization{updateLocale(locale: "%s", autoUpdate: true, namespacing: false, namespaces: []){responseResult{errorCode}}}}'
                    % LOCALE))

        self._session.execute(
            dsl_gql(
                DSLMutation(
                    self._dslschema.Mutation.groups.select(
                        self._dslschema.GroupMutation.update(
                            id=2,
                            name='Guests',
                            redirectOnLogin='',
                            permissions=['read:pages', 'read:assets'],
                            pageRules=[{
                                'deny': False,
                                'id': 'Migration-Home',
                                'locales': [],
                                'match': 'START',
                                'path': 'home',
                                'roles': ['read:pages']
                            }, {
                                'deny': False,
                                'id': 'Migration-Start',
                                'locales': [],
                                'match': 'START',
                                'path': LDAP_USER_GROUP_REDIRECT_URI.replace('/', ''),
                                'roles': ['read:pages']
                            }, {
                                'deny': False,
                                'id': 'Migration-assets',
                                'locales': [],
                                'match': 'START',
                                'path': 'assets',
                                'roles': ['read:assets']
                            }],
                        ).select(
                            self._dslschema.DefaultResponse.responseResult.
                            select(
                                self._dslschema.ResponseStatus.succeeded))))))

        self._session.execute(
            dsl_gql(
                DSLMutation(
                    self._dslschema.Mutation.pages.select(
                        self._dslschema.PageMutation.create(
                            content='Nothing.',
                            description='',
                            editor='markdown',
                            isPublished=True,
                            isPrivate=False,
                            locale=LOCALE,
                            path='/home',
                            scriptJs=
                            '<script>window.location.href = "{}"</script>'.
                            format(LDAP_USER_GROUP_REDIRECT_URI),
                            tags=[],
                            title='Home',
                        ).select(
                            self._dslschema.PageResponse.responseResult.select(
                                self._dslschema.ResponseStatus.succeeded))))))


def main():
    migration = MediawikiMigration(MEDIAWIKI_HOST, MEDIAWIKI_SSH_USER,
                                   MEDIAWIKI_SSH_PASSWD, WIKIJS_HOST,
                                   WIKIJS_TOKEN, MEDIAWIKI_SSH_PORT)
    migration.set_defaults()
    if not os.path.exists(WIKI_XML_LOCATION):
        migration.download_wiki_dump(WIKI_XML_LOCATION)
    if IMPORT_LDAP.lower() == 'true':
        migration.import_ldap_users()
    migration.import_users_from_wiki()
    migration.update_timezone_of_all_users(USER_TIMEZONE)
    if MEDIAWIKI_ASSETS:
        migration.migrate_assets()
    page_blacklist = []
    try:
        with open('/page_blacklist.txt', 'r') as f:
            page_blacklist=f.read().splitlines()
    except FileNotFoundError:
        logger.info('No page blacklist provided.')
    migration.migrate(page_blacklist=page_blacklist)


if __name__ == '__main__':
    main()
