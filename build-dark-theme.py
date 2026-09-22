#!/usr/bin/env python3
"""Generate frontend/src/shared/dark-theme.css from the existing light styles.

Why a generator: frontend/src/shared/style.css contains 335 colour literals with
309 distinct values, so a hand-written dark theme would drift out of sync on the
next UI change. This script re-derives a dark override for every coloured
declaration found in style.css and in the <style> blocks of the Vue components.

How it stays safe:
* Light mode never reads these rules: EVERY selector of every generated rule is
  prefixed with ``html.dark`` (``:root`` becomes ``html.dark``). The guard at the
  end of main() enforces this, because a comma list such as
  ``.work-toolbar input, .work-toolbar select`` once leaked its second selector
  unprefixed and changed the light appearance.
* Colours are transformed in HLS space: surfaces get darker, text gets lighter,
  borders get dimmer and box shadows become black, keeping each colour's hue.

Run (after UI colour changes):  python build-dark-theme.py
"""
from __future__ import annotations

import colorsys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'frontend/src'
OUT = SRC / 'shared/dark-theme.css'

HEX = re.compile(r'#[0-9a-fA-F]{3,8}\b')
# CSS colour keywords actually used by this project (style.css uses "white" for
# several surfaces). Kept to light/dark neutrals so every entry maps cleanly.
NAMED_COLOURS = {
    'white': '#ffffff', 'whitesmoke': '#f5f5f5', 'ghostwhite': '#f8f8ff',
    'snow': '#fffafa', 'ivory': '#fffff0', 'floralwhite': '#fffaf0',
    'seashell': '#fff5ee', 'linen': '#faf0e6', 'oldlace': '#fdf5e6',
    'cornsilk': '#fff8dc', 'beige': '#f5f5dc', 'azure': '#f0ffff',
    'mintcream': '#f5fffa', 'honeydew': '#f0fff0', 'aliceblue': '#f0f8ff',
    'lavenderblush': '#fff0f5', 'mistyrose': '#ffe4e1', 'lightyellow': '#ffffe0',
    'gainsboro': '#dcdcdc', 'silver': '#c0c0c0', 'gray': '#808080',
    'grey': '#808080', 'black': '#000000',
}
NAMED = re.compile(r'\b(' + '|'.join(NAMED_COLOURS) + r')\b', re.I)
COMMENT = re.compile(r'/\*.*?\*/', re.S)
STYLE_BLOCK = re.compile(r'<style[^>]*>(.*?)</style>', re.S)
ROOT_SELECTORS = (':root', 'html')


def parse_hex(text: str):
    body = text.lstrip('#')
    if len(body) in (3, 4):
        body = ''.join(ch * 2 for ch in body)
    if len(body) not in (6, 8):
        return None
    red, green, blue = (int(body[i:i + 2], 16) / 255 for i in (0, 2, 4))
    alpha = int(body[6:8], 16) / 255 if len(body) == 8 else 1.0
    return red, green, blue, alpha


def format_rgb(rgb, alpha: float) -> str:
    red, green, blue = (max(0, min(255, round(channel * 255))) for channel in rgb)
    if alpha >= 0.999:
        return f'#{red:02x}{green:02x}{blue:02x}'
    return f'rgba({red},{green},{blue},{alpha:.2f})'


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalise_named(value: str) -> str:
    """Rewrite CSS colour keywords to hex so they go through the same transform."""
    return NAMED.sub(lambda match: NAMED_COLOURS[match.group(0).lower()], value)


def role_of(prop: str) -> str:
    name = prop.strip().lower()
    if name.startswith('--'):
        if 'primary' in name:
            return 'brand_dark' if 'dark' in name else 'brand'
        if 'muted' in name or 'text' in name:
            return 'text'
        if 'line' in name or 'border' in name:
            return 'line'
        return 'surface'
    if name.startswith('background'):
        return 'surface'
    if name.startswith('color'):
        return 'text'
    if name.startswith('border'):
        return 'line'
    if name.startswith('box-shadow') or name.startswith('text-shadow'):
        return 'shadow'
    if name.startswith('outline'):
        return 'faint'
    return 'none'


def dark_colour(literal: str, role: str) -> str:
    parsed = parse_hex(literal)
    if parsed is None:
        return literal
    red, green, blue, alpha = parsed
    hue, light, sat = colorsys.rgb_to_hls(red, green, blue)

    if role == 'surface':
        if light >= 0.90:
            new_light, new_sat = 0.145, min(sat * 0.6, 0.18)
        elif light >= 0.78:
            new_light, new_sat = 0.19, min(sat * 0.75, 0.22)
        elif light >= 0.60:
            new_light, new_sat = 0.245, min(sat * 0.8, 0.26)
        else:
            new_light, new_sat = clamp(light * 0.8, 0.16, 0.40), min(sat, 0.35)
    elif role == 'text':
        if light >= 0.92:
            new_light, new_sat = light, sat          # keep near-white text
        elif light >= 0.72:
            new_light, new_sat = 0.62, min(sat * 0.7, 0.30)
        elif light >= 0.45:
            new_light, new_sat = 0.78, min(sat * 0.85, 0.40)
        else:
            new_light, new_sat = 0.90, min(sat * 0.8, 0.45)
    elif role == 'line':
        new_light, new_sat = (0.27 if light >= 0.85 else 0.33), min(sat * 0.8, 0.28)
    elif role == 'brand':
        new_light, new_sat = clamp(light + 0.12, 0.55, 0.78), clamp(sat, 0.25, 0.60)
    elif role == 'brand_dark':
        new_light, new_sat = clamp(light + 0.02, 0.46, 0.68), clamp(sat, 0.25, 0.60)
    elif role == 'shadow':
        return format_rgb((0.0, 0.0, 0.0), alpha if alpha < 1 else 0.45)
    elif role == 'faint':
        new_light, new_sat = clamp(light + 0.10, 0.50, 0.80), min(sat, 0.40)
    else:
        return literal

    rgb = colorsys.hls_to_rgb(hue, clamp(new_light, 0.0, 1.0), clamp(new_sat, 0.0, 1.0))
    return format_rgb(rgb, alpha)


def split_blocks(css: str):
    """Yield (prelude, body) pairs, keeping nested blocks inside their body."""
    blocks, prelude, body, depth = [], '', '', 0
    for char in css:
        if char == '{':
            depth += 1
            if depth == 1:
                prelude, body = prelude.strip(), ''
            else:
                body += char
        elif char == '}':
            depth -= 1
            if depth == 0:
                blocks.append((prelude, body))
                prelude = ''
            else:
                body += char
        elif depth == 0:
            prelude += char
        else:
            body += char
    return blocks


def convert_decls(body: str):
    converted = []
    for chunk in body.split(';'):
        if ':' not in chunk:
            continue
        prop, value = chunk.split(':', 1)
        prop, value = prop.strip(), value.strip()
        normalised = normalise_named(value)
        if not prop or not HEX.search(normalised):
            continue
        role = role_of(prop)
        if role == 'none':
            continue
        replaced = HEX.sub(lambda match: dark_colour(match.group(0), role), normalised)
        if replaced != value:
            converted.append((prop, replaced))
    return converted


def scoped_selector(prelude: str) -> str:
    """Prefix every selector in a comma list so no rule can escape html.dark."""
    parts = [part.strip() for part in prelude.split(',') if part.strip()]
    return ', '.join('html.dark' if part in ROOT_SELECTORS else f'html.dark {part}'
                     for part in parts)


def render(css: str, prefix: str = '') -> list[str]:
    lines: list[str] = []
    for prelude, body in split_blocks(css):
        if prelude.startswith('@'):
            nested = render(body, prefix)
            if nested:
                lines.append(f'{prefix}{prelude}{{')
                lines.extend(f'  {line}' for line in nested)
                lines.append(f'{prefix}}}')
            continue
        decls = convert_decls(body)
        if not decls:
            continue
        declarations = ''.join(f'{prop}:{value};' for prop, value in decls)
        lines.append(f'{prefix}{scoped_selector(prelude)}{{{declarations}}}')
    return lines


def main() -> None:
    chunks = [(SRC / 'shared/style.css').read_text(encoding='utf-8')]
    for path in sorted(SRC.rglob('*.vue')):
        for block in STYLE_BLOCK.finditer(path.read_text(encoding='utf-8')):
            chunks.append(block.group(1))

    lines: list[str] = []
    for css in chunks:
        lines.extend(render(COMMENT.sub('', css)))

    # Guard: refuse to emit a rule that could affect the light theme.
    for line in lines:
        head = line.split('{', 1)[0]
        if line.startswith('@') or head.startswith('  ') or head.strip() == '}':
            continue
        for part in head.split(','):
            if part.strip() and not part.strip().startswith('html.dark'):
                raise SystemExit(f'ABORT: selector escaped the dark scope: {line[:90]}')

    header = (
        '/* 数伴深色主题覆盖：由 build-dark-theme.py 自动生成，请勿手动编辑。\n'
        '   来源：frontend/src/shared/style.css 与各组件 <style> 块。\n'
        '   重新生成：python build-dark-theme.py\n'
        '   浅色模式不使用本文件（每条规则的每个选择器都以 html.dark 开头）。 */\n'
    )
    OUT.write_text(header + '\n'.join(lines) + '\n', encoding='utf-8')
    print(f'wrote {OUT.relative_to(ROOT)} with {len(lines)} rules')


if __name__ == '__main__':
    main()
