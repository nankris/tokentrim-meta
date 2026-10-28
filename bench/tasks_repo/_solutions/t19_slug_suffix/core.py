import re
import unicodedata
def unique_slug(title, used):
    ascii_title = unicodedata.normalize('NFKD',title).encode('ascii','ignore').decode()
    base = re.sub('[^a-z0-9]+','-',ascii_title.lower()).strip('-') or 'item'
    used = set(used)
    candidate, suffix = base, 2
    while candidate in used:
        candidate = f'{base}-{suffix}'
        suffix += 1
    return candidate
def slug_path(slug):
    return '/articles/' + slug
