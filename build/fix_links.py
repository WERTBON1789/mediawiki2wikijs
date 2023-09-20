#!/usr/bin/env python3
import re

def fix_hyper_links(content: str):
    split_content = content.splitlines()

    for index, line in enumerate(split_content):
        split_content[index], num = re.subn(r"\[(.+?)\]\(Media:(.+?) \"wikilink\"\)",
            lambda m: '[{}](/assets/{} "{}")'.format(
                m.group(1),
                m.group(2).lower(),
                m.group(1).replace('"', '')), line)
        if num > 0:
            continue

        split_content[index], num = re.subn(r"\[(.+?)\]\((.+?) \"wikilink\"\)",
            lambda m: '[{}](/{} "{}")'.format(
                m[1].replace(':', '/').strip(),
                re.sub("(?<=#)(.*)", lambda m2: m2[1].lower(), m[2].replace(':', '/').replace('.', '_')),
                m[1].replace(':', '/').replace('"', r'\"').replace('\'', r'\'')), line)
        if num > 0:
            continue

        split_content[index], num = re.subn("<a href=\"(.+?)\".*>(.+)</a>",
            lambda m: '<a href="/{0}" title="{1}">{1}</a>'.format(
                m[1].replace(':', '/'),
                m[2]), line)
        if num > 0:
            continue

        split_content[index], num = re.subn(r"\!\[(.*)\]\((.+) \"(.+)\"\)",
            lambda m: '![{}](/assets/{} "{}")'.format(
                m[1],
                m[2].lower(),
                m[3].replace('"', r'\"').replace('\'', r'\'')), line)
        if num > 0:
            continue

        split_content[index], num = re.subn(r"<img src=\"(.+)\" title=\"(.+?)\"(.*?)/>",
            lambda m: '<img src="/assets/{0}" title="{1}" {2} />'.format(
                m[1].lower(),
                m[2],
                m[3]), line)

    content = '\n'.join(split_content)

    return content
