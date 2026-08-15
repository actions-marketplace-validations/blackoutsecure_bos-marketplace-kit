"""Render a Marketplace-style branding card SVG.

Called by the `branding-preview` composite. Reads the icon body from
stdin (the feather icon's inner SVG), composes a 256x256 card with
the configured colour pair, and writes to the provided output path.

CLI:
    render_card.py <out_path> <icon_name> <color_name> <bg_hex> <fg_hex>
The icon body is read from stdin.
"""

from __future__ import annotations

import sys

TEMPLATE = '''\
<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256" role="img" aria-label="Marketplace card preview for {icon} on {color}">
  <rect width="256" height="256" fill="{bg}" rx="12" ry="12"/>
  <g transform="translate(80, 80) scale(4)" fill="none" stroke="{fg}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    {inner}
  </g>
  <text x="128" y="220" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" font-size="14" font-weight="600" text-anchor="middle" fill="{fg}" opacity="0.85">{icon} · {color}</text>
</svg>
'''


def main() -> int:
    out_path, icon, color, bg, fg = sys.argv[1:6]
    inner = sys.stdin.read().strip()
    if not inner:
        sys.stderr.write("error: empty icon body from stdin\n")
        return 1
    svg = TEMPLATE.format(icon=icon, color=color, bg=bg, fg=fg, inner=inner)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
