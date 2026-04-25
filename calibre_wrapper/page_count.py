import math
import re
import subprocess
import zipfile
from xml.etree import ElementTree as ET

CHARS_PER_PAGE = 1024

OPF_NS = {
    'opf': 'http://www.idpf.org/2007/opf',
    'container': 'urn:oasis:names:tc:opendocument:xmlns:container',
}

PDF_PAGES_RE = re.compile(r'^Pages:\s+(\d+)\s*$', re.MULTILINE)


def extract_page_count(file_path, fmt):
    fmt = (fmt or '').upper()
    try:
        if fmt == 'PDF':
            return _pdf_page_count(file_path)
        if fmt == 'EPUB':
            return _epub_page_count(file_path)
    except Exception as e:
        print('page_count extraction failed for %s (%s): %s' % (file_path, fmt, e), flush=True)
    return None


def _pdf_page_count(file_path):
    res = subprocess.run(['pdfinfo', file_path], capture_output=True, timeout=30)
    if res.returncode != 0:
        return None
    m = PDF_PAGES_RE.search(res.stdout.decode(errors='replace'))
    return int(m.group(1)) if m else None


def _epub_page_count(file_path):
    with zipfile.ZipFile(file_path) as zf:
        opf_path = _find_opf_path(zf)
        if not opf_path:
            return None
        with zf.open(opf_path) as f:
            opf = ET.parse(f).getroot()

        for meta in opf.iter('{%s}meta' % OPF_NS['opf']):
            if meta.get('name') == 'calibre:num_pages':
                content = meta.get('content')
                if content and content.isdigit():
                    return int(content)

        return _epub_count_by_chars(zf, opf, opf_path)


def _find_opf_path(zf):
    try:
        with zf.open('META-INF/container.xml') as f:
            container = ET.parse(f).getroot()
        rootfile = container.find('.//container:rootfile', OPF_NS)
        if rootfile is not None:
            return rootfile.get('full-path')
    except KeyError:
        pass
    for name in zf.namelist():
        if name.lower().endswith('.opf'):
            return name
    return None


def _epub_count_by_chars(zf, opf, opf_path):
    manifest = {}
    for item in opf.iter('{%s}item' % OPF_NS['opf']):
        manifest[item.get('id')] = item.get('href')

    spine = opf.find('{%s}spine' % OPF_NS['opf'])
    if spine is None:
        return None

    opf_dir = opf_path.rsplit('/', 1)[0] if '/' in opf_path else ''
    total_chars = 0
    for itemref in spine.iter('{%s}itemref' % OPF_NS['opf']):
        idref = itemref.get('idref')
        href = manifest.get(idref)
        if not href:
            continue
        full = '%s/%s' % (opf_dir, href) if opf_dir else href
        try:
            with zf.open(full) as f:
                total_chars += _count_text_chars(f.read())
        except KeyError:
            continue

    if total_chars == 0:
        return None
    return max(1, math.ceil(total_chars / CHARS_PER_PAGE))


def _count_text_chars(raw_bytes):
    try:
        text = raw_bytes.decode('utf-8', errors='replace')
    except Exception:
        return 0
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return len(text)
