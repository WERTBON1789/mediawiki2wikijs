#!/usr/bin/env python3
import os

WIKIJS_HOST                  = os.environ.get("WIKIJS_HOST")
WIKIJS_TOKEN                 = os.environ.get("WIKIJS_TOKEN")
MEDIAWIKI_HOST               = os.environ.get("MEDIAWIKI_SSH_HOST")
MEDIAWIKI_SSH_PORT           = os.environ.get("MEDIAWIKI_SSH_PORT")
MEDIAWIKI_SSH_PASSWD         = os.environ.get("MEDIAWIKI_SSH_PASSWD")
MEDIAWIKI_SSH_USER           = os.environ.get("MEDIAWIKI_SSH_USER")
PSQL_HOST                    = os.environ.get("PSQL_HOST")
PSQL_PORT                    = os.environ.get("PSQL_PORT")
LDAP_HOST                    = os.environ.get("LDAP_HOST")
LDAP_ADMIN_DN                = os.environ.get("LDAP_ADMIN_DN")
LDAP_ADMIN_PASSWD            = os.environ.get("LDAP_ADMIN_PASSWD")
LDAP_USER_DN                 = os.environ.get("LDAP_USER_DN")
LDAP_USER_FILTER             = os.environ.get("LDAP_USER_FILTER")
LDAP_GROUP_DN                = os.environ.get("LDAP_GROUP_DN")
LDAP_GROUP_FILTER            = os.environ.get("LDAP_GROUP_FILTER")
LDAP_USER_GROUPS             = os.environ.get("LDAP_USER_GROUPS")
LDAP_ADMIN_GROUP             = os.environ.get("LDAP_ADMIN_GROUP")
IMPORT_LDAP                  = os.environ.get("IMPORT_LDAP")
MEDIAWIKI_ASSETS             = os.environ.get("MEDIAWIKI_ASSETS")
USER_TIMEZONE                = os.environ.get("USER_TIMEZONE")
LDAP_USER_GROUP_REDIRECT_URI = os.environ.get("LDAP_USER_GROUP_REDIRECT_URI")
LOCALE                       = os.environ.get("LOCALE")

WIKI_XML_LOCATION = "/data/wiki.xml"
WIKI_MD_DIR       = "/data/wiki-md"
WIKI_TXT_DIR      = "/data/wiki-txt"
MIGRATION_LOG     = "/data/wiki-migration.log"
ERR_PAGES_LOG     = "/data/err-pages.log"
WIKI_IMG_LOCATION = "/data/wiki-img.tar.gz"
ASSET_FOLDER      = "assets"
DUMP_OBJ          = "/data/dump.bin"

