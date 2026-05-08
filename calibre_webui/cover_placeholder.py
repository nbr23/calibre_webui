import hashlib
from xml.sax.saxutils import escape as xml_escape

from flask import Response


PALETTES = [
    ('#f4ead8', '#7a4f1d'),
    ('#e2e6d4', '#3e5641'),
    ('#efd9d4', '#6b2737'),
    ('#dde4ec', '#2a3a5a'),
    ('#ead7b8', '#704214'),
    ('#e1d8e6', '#4b3869'),
    ('#d4e6dc', '#2f5e4a'),
    ('#f0dac6', '#9c4a1f'),
]


def _wrap(text, max_chars, max_lines):
    text = (text or '').strip()
    if not text:
        return []
    words = text.split()
    lines, current = [], ''
    for word in words:
        if len(word) > max_chars:
            word = word[:max_chars - 1] + '…'
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current += ' ' + word
        else:
            lines.append(current)
            if len(lines) >= max_lines:
                current = ''
                break
            current = word
    if current and len(lines) < max_lines:
        lines.append(current)
    if lines and len(' '.join(lines)) < len(text):
        last = lines[-1]
        if len(last) >= max_chars:
            lines[-1] = last[:max_chars - 1] + '…'
        else:
            lines[-1] = last + '…'
    return lines


def _ornament(style, accent):
    if style == 0:
        return (
            f'<path d="M0 0 L80 0 L62 18 L18 18 L18 62 L0 80 Z" fill="{accent}"/>'
            f'<path d="M540 0 L460 0 L478 18 L522 18 L522 62 L540 80 Z" fill="{accent}"/>'
            f'<path d="M0 720 L0 640 L18 658 L18 702 L62 702 L80 720 Z" fill="{accent}"/>'
            f'<path d="M540 720 L540 640 L522 658 L522 702 L478 702 L460 720 Z" fill="{accent}"/>'
        )
    if style == 1:
        return (
            f'<rect x="22" y="22" width="496" height="676" fill="none" stroke="{accent}" stroke-width="3"/>'
            f'<rect x="32" y="32" width="476" height="656" fill="none" stroke="{accent}" stroke-width="1"/>'
            f'<circle cx="22" cy="22" r="6" fill="{accent}"/>'
            f'<circle cx="518" cy="22" r="6" fill="{accent}"/>'
            f'<circle cx="22" cy="698" r="6" fill="{accent}"/>'
            f'<circle cx="518" cy="698" r="6" fill="{accent}"/>'
        )
    if style == 2:
        return (
            f'<rect x="0" y="60" width="540" height="40" fill="{accent}"/>'
            f'<rect x="0" y="108" width="540" height="2" fill="{accent}"/>'
            f'<rect x="0" y="610" width="540" height="2" fill="{accent}"/>'
            f'<rect x="0" y="620" width="540" height="40" fill="{accent}"/>'
        )
    if style == 3:
        return (
            f'<polygon points="40,80 80,40 460,40 500,80 500,640 460,680 80,680 40,640" '
            f'fill="none" stroke="{accent}" stroke-width="3"/>'
            f'<polygon points="52,86 86,52 454,52 488,86 488,634 454,668 86,668 52,634" '
            f'fill="none" stroke="{accent}" stroke-width="1"/>'
        )
    return (
        f'<line x1="60" y1="80" x2="240" y2="80" stroke="{accent}" stroke-width="2"/>'
        f'<line x1="300" y1="80" x2="480" y2="80" stroke="{accent}" stroke-width="2"/>'
        f'<polygon points="270,66 284,80 270,94 256,80" fill="{accent}"/>'
        f'<line x1="60" y1="640" x2="240" y2="640" stroke="{accent}" stroke-width="2"/>'
        f'<line x1="300" y1="640" x2="480" y2="640" stroke="{accent}" stroke-width="2"/>'
        f'<polygon points="270,626 284,640 270,654 256,640" fill="{accent}"/>'
    )


def _svg(book_id, title, authors):
    h = int(hashlib.md5(str(book_id).encode()).hexdigest(), 16)
    base, accent = PALETTES[h % len(PALETTES)]
    style = (h >> 8) % 5
    seed = (h >> 16) % 200

    title_lines = _wrap(title or 'Untitled', max_chars=14, max_lines=3) or ['Untitled']
    author = (authors or '').split(';')[0].strip() if authors else ''
    author_lines = _wrap(author or 'Unknown author', max_chars=22, max_lines=2)

    title_block_h = (len(title_lines) - 1) * 48
    title_y0 = 340 - title_block_h // 2
    title_tspans = ''.join(
        f'<tspan x="270" dy="{0 if i == 0 else 48}">{xml_escape(line)}</tspan>'
        for i, line in enumerate(title_lines)
    )

    author_y0 = title_y0 + title_block_h + 70
    author_tspans = ''.join(
        f'<tspan x="270" dy="{0 if i == 0 else 28}">{xml_escape(line)}</tspan>'
        for i, line in enumerate(author_lines)
    )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 540 720" '
        'preserveAspectRatio="xMidYMid slice">'
        '<defs>'
        f'<filter id="g" x="0%" y="0%" width="100%" height="100%">'
        f'<feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" '
        f'stitchTiles="stitch" seed="{seed}"/>'
        '<feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.18 0"/>'
        '</filter>'
        '</defs>'
        f'<rect width="540" height="720" fill="{base}"/>'
        '<rect width="540" height="720" filter="url(#g)"/>'
        f'{_ornament(style, accent)}'
        f'<text x="270" y="{title_y0}" text-anchor="middle" fill="{accent}" '
        'font-family="Georgia, &quot;Times New Roman&quot;, serif" '
        f'font-size="36" font-weight="700">{title_tspans}</text>'
        f'<text x="270" y="{author_y0}" text-anchor="middle" fill="{accent}" '
        'font-family="Georgia, &quot;Times New Roman&quot;, serif" '
        f'font-size="22" font-style="italic" opacity="0.85">{author_tspans}</text>'
        '</svg>'
    )


def cover_placeholder_response(book_id, title=None, authors=None):
    resp = Response(_svg(book_id, title, authors), mimetype='image/svg+xml')
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp
