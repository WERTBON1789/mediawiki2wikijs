#!/usr/bin/env python3
import re

def fix_hyper_links(content: str):
    split_content = content.splitlines()

    for index, line in enumerate(split_content):
        regex = re.search(r"\[(.+)\]\(Media:(.+) \"wikilink\"\)", line)
        if regex is not None:
            split_content[index] = re.sub(
                r"\[.+\]\(Media:.+ \"wikilink\"\)",
                '[{}](/assets/{} "{}")'.format(
                    regex.group(1),
                    regex.group(2).lower(),
                    regex.group(1).replace('"', '')), line)
            continue
        regex = re.search(r"\[(.+)\]\((.+) \"wikilink\"\)", line)
        if regex is not None:
            tmp = regex.group(2) \
                .replace(':', '/') \
                .replace('.', '_').split('#')
            if len(tmp) > 1:
                tmp[-1] = tmp[-1].lower()
            tmp = '#'.join(tmp)
            split_content[index] = re.sub(
                r"\[.+\]\(.+ \"wikilink\"\)", '[{}](/{} "{}")'.format(
                    regex.group(1).replace(':', '/').strip(), tmp,
                    regex.group(1) \
                        .replace(':', '/') \
                        .replace('"', r'\"') \
                        .replace('\'', r'\'')), line)
            continue
        regex = re.search("<a href=\"(.+?)\".*>(.+)</a>", line)
        if regex is not None:
            split_content[index] = re.sub(
                "<a href=\".+?\".*>.+</a>",
                '<a href="/{0}" title="{1}">{1}</a>'.format(
                    regex.group(1).replace(':', '/'),
                    regex.group(2)), line)
            continue
        regex = re.search(r"\!\[(.*)\]\((.+) \"(.+)\"\)", line)
        if regex is not None:
            split_content[index] = re.sub(
                r"\!\[.*\]\(.+ \".+\"\)", '![{}](/assets/{} "{}")'.format(
                    regex.group(1),
                    regex.group(2).lower(),
                    regex.group(3).replace('"',
                                           r'\"').replace('\'', r'\'')),
                line)
            continue
        regex = re.search(r"<img src=\"(.+)\" title=\"(.+?)\"(.*?)/>",
                          line)
        if regex is not None:
            split_content[index] = re.sub(
                r"<img src=\".+\" title=\".+?\".*?/>",
                '<img src="/assets/{0}" title="{1}" {2} />'.format(
                    regex.group(1).lower(), regex.group(2),
                    regex.group(3)), line)

    content = '\n'.join(split_content)

    return content
