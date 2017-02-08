"""Utils for analyzing Princeton Web Census data."""
from BlockListParser import BlockListParser
from ipaddress import ip_address
from publicsuffix import PublicSuffixList, fetch
from urllib.parse import urlparse

import json

# Execute on module load
psl_file = fetch()
psl = PublicSuffixList(psl_file)
el_parser = BlockListParser('easylist.txt')
ep_parser = BlockListParser('easyprivacy.txt')

with open('org_domains.json', 'r') as f:
    org_domains = json.load(f)

class CensusUtilsException(Exception):
    pass

def get_domain(url):
    """Strip the URL down to just a hostname+publicsuffix.

    If the provided url contains an IP address, the IP address is returned.
    """

    hostname = urlparse(url).hostname
    try:
        ip_address(hostname)
        return hostname
    except ValueError:
        return psl.get_public_suffix(hostname)
    
def is_tracker(url, is_js=False, is_img=False, 
               first_party=None, blocklist='easylist'):
    """Return a bool determining if a given url is a tracker in the given
    first party context (if first_party provided)."""
    
    if blocklist == 'easylist':
        parser = el_parser
    elif blocklist == 'easyprivacy':
        parser = ep_parser
    else:
        raise CensusUtilsException("You must provide a supported blocklist: easylist, easyprivacy")
        
    options = dict()
    if first_party:
        fp_domain = get_domain(first_party)
        url_domain = get_domain(url)

        if url_domain != fp_domain:
            options['third-party'] = True
        options['domain'] = fp_domain
    options['image'] = is_img
    options['script'] = is_js

    return parser.should_block(url, options)

def get_trackers(url_list, first_party, blocklist_parser=None, blocklist="easylist.txt"):
    """Identify domains that are identified as trackers from list of URLs.

    Returns set of domains/IPs filtered by the given blocklist_parser.
    TODO: Better to return set of domains/IPs, or list of filtered urls?
    """
    if not blocklist_parser:
        blocklist_parser = BlockListParser(blocklist)

    filtered_domains = set()
    for url in url_list:
        if is_tracker(url, first_party, blocklist_parser):
            filtered_domains.add(get_domain(url))

    return filtered_domains

def get_org(url):
    """If possible, find the name of the organization owning this particular URL/domain.
    
    If no organization is found, return none.
    """
    url_domain = get_domain(url)
    organization = None

    for org in org_domains:
        try:
            if url_domain in org[u'domains']:
                organization = org[u'organization']
        except KeyError:
            continue
     
    return organization
        
    

def should_ignore(url):
    """
    These urls are generated by the browser or extensions.
    Most should be absent from new data.
    """
    return (url == 'https://tiles.services.mozilla.com/v3/links/fetch/en-US/release' or
            url == 'https://location.services.mozilla.com/v1/country?key=7e40f68c-7938-4c5d-9f95-e61647c213eb' or
            url == 'https://cmp-cdn.ghostery.com/check?os=linux&gr=opt-out&ua=firefox&v=0' or
            url == 'https://search.services.mozilla.com/1/firefox/41.0.2/release/en-US/US/default/default' or
            url == 'https://d.ghostery.com/upgrade?gr=0&v=5.4.10&os=linux&ua=ff' or
            url.startswith('https://easylist-downloads.adblockplus.org/easylist.txt') or
            url.startswith('https://aus4.mozilla.org/update/') or
            url.startswith('https://tiles-cloudfront.cdn.mozilla.net'))
#########################################################
# Utilities for interpreting content type of resources
#########################################################

content_type_map = {
    'script': lambda x: (
        'javascript' in x
        or 'ecmascript' in x
        or x.endswith('text/js')
    ),
    'image': lambda x: (
        'image' in x
        or 'img' in x
        or 'jpg' in x
        or 'jpeg' in x
        or 'gif' in x
        or 'png' in x
        or 'ico' in x
    ),
    'video': lambda x: (
        ('video' in x
        or 'movie' in x
        or 'mp4' in x
        or 'webm' in x)
        and 'flv' not in x
    ),
    'css': lambda x: 'css' in x,
    'html': lambda x: 'html' in x,
    'plain': lambda x: 'plain' in x and 'html' not in x,
    'font': lambda x: 'font' in x or 'woff' in x,
    'json': lambda x: 'json' in x,
    'xml': lambda x: 'xml' in x and 'image' not in x,
    'flash': lambda x: 'flash' in x or 'flv' in x or 'swf' in x,
    'audio': lambda x: 'audio' in x,
    'stream': lambda x: 'octet-stream' in x,
    'form': lambda x: 'form' in x,
    'binary': lambda x: 'binary' in x and 'image' not in x
}

IMAGE_TYPES = {'tif', 'tiff', 'gif', 'jpeg',
               'jpg', 'jif', 'jfif', 'jp2',
               'jpx', 'j2k', 'j2c', 'fpx',
               'pcd', 'png'}


def get_top_level_type(content_type):
    """Returns a "top level" type for a given mimetype string.
    This uses a manually compiled mapping of mime types. The top level types
    returned around true top level types
    """
    if ';' in content_type:
        content_type = content_type.split(';')[0]
    for k,v in content_type_map.items():
        if v(content_type.lower()):
            return k
    return None

def is_passive(content_type):
    """Checks if content is considered passive content by Firefox's
    mixed content blocker.
    Note that browsers block on *request* context, not response. For example,
    the request generated from a <script> element will be classified as active
    content. Since we only have access to responses, we use a custom mapping.
    Passive content as defined here (ignoring <object> subresources):
        https://developer.mozilla.org/en-US/docs/Security/Mixed_content
    """
    return get_top_level_type(content_type) in ['image','audio','video']

def is_active(content_type):
    """Checks if content is considered active content by Firefox's
    mixed content blocker.
    Note that browsers block on *request* context, not response. For example,
    the request generated from a <script> element will be classified as active
    content. Since we only have access to responses, we use a custom mapping.
    Active content is any content not falling within the few passive content
    types.
    """
    return not is_passive(content_type)

def is_img(url, content_type):
    if get_top_level_type(content_type) == 'image':
        return True
    extension = urlparse(url).path.split('.')[-1]
    if extension.lower() in IMAGE_TYPES:
        return True
    return False

def is_js(url, content_type):
    if get_top_level_type(content_type) == 'script':
        return True
    if urlparse(url).path.split('.')[-1].lower() == 'js':
        return True
    return False
