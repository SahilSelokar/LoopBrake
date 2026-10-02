"""Fetch, check and shrink the dashboard's fonts and icons (development only; research R6).

    uv run --with fonttools --with brotli python scripts/vendor_assets.py

Downloads pinned files from their official sources, checks each sha256, subsets the fonts to Latin
as woff2, builds one SVG sprite of the Lucide icons the dashboard uses, and writes everything to
src/loopbrake/static/. The outputs are committed; users never run this (Principle VI: the page loads
nothing from the network).
"""
import hashlib
import io
import re
import tarfile
import urllib.request
from pathlib import Path

STATIC = Path(__file__).parents[1] / "src" / "loopbrake" / "static"
FONTS_COMMIT = "9710da1eacb3be272583c3224dcb70f9da6eadbb"  # google/fonts main, 2026-09-30
FONTS = {  # output name -> (path in google/fonts, sha256)
    "inter-tight": ("ofl/intertight/InterTight%5Bwght%5D.ttf", "b81b73dcb64df3c230cabade7df6c5773bf863233f24c9ee51087519f1f88b6f"),
    "jetbrains-mono": ("ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf", "48715a42ec242c21e9f02692891e147d022299a52e48d5e413e1a942193ffeda"),
    "instrument-serif-italic": ("ofl/instrumentserif/InstrumentSerif-Italic.ttf", "08939b8bdf534afec24ae0ef5e03f948940cd9a8fe08e7fecbad040e62327385"),
}
LICENSES = {  # family -> (path, sha256)
    "Inter Tight": ("ofl/intertight/OFL.txt", "50240ab035cf1b6b3307940235481d515c4b6de3ab1fa843dbe59e7892cb9d58"),
    "JetBrains Mono": ("ofl/jetbrainsmono/OFL.txt", "b2fe5e8987594e9ffd1d2ca52a2f5d73eb8335243893c5d6254b5ad69269591d"),
    "Instrument Serif": ("ofl/instrumentserif/OFL.txt", "129ed7618959716959f2941fdd5b49e0ad6e6c1d78726761786a00253d865521"),
}
LUCIDE_VERSION = "1.49.0"
LUCIDE_SHA256 = "c8c9d5dcbc50f388afea623ce2bcbef5788eb0b2d084081aa52d6adaae4ebba3"
ICONS = ["play", "loader-circle", "octagon-x", "check", "triangle-alert", "repeat", "gauge", "shield-check",
         "activity", "layers", "coins", "clock", "funnel", "search", "settings", "external-link", "download",
         "square-terminal", "sparkles", "send", "x", "chevron-left", "circle-alert", "house", "folder", "copy",
         "blend", "chart-column", "wrench"]
# Basic Latin, Latin-1, and the punctuation the UI uses: dashes, quotes, bullet, ellipsis, arrow, minus.
UNICODES = list(range(0x20, 0x7F)) + list(range(0xA0, 0x100)) + [0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D,
                                                                  0x2022, 0x2026, 0x2192, 0x2212, 0x00B7]


def fetch(url, sha):
    data = urllib.request.urlopen(url, timeout=60).read()
    got = hashlib.sha256(data).hexdigest()
    if got != sha:
        raise SystemExit(f"sha256 mismatch for {url}: {got}")
    return data, url


def subset(ttf, out):
    from fontTools import subset as fs
    from fontTools.ttLib import TTFont

    font = TTFont(io.BytesIO(ttf))
    opts = fs.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    sub = fs.Subsetter(opts)
    sub.populate(unicodes=UNICODES)
    sub.subset(font)
    font.flavor = "woff2"
    font.save(out)


def main():
    raw = f"https://raw.githubusercontent.com/google/fonts/{FONTS_COMMIT}/"
    (STATIC / "fonts").mkdir(parents=True, exist_ok=True)
    sources = []
    for name, (path, sha) in FONTS.items():
        data, url = fetch(raw + path, sha)
        subset(data, STATIC / "fonts" / f"{name}.woff2")
        sources.append((f"fonts/{name}.woff2", url, sha))
    texts = []
    for family, (path, sha) in LICENSES.items():
        data, url = fetch(raw + path, sha)
        texts.append(f"{family}\n{'=' * len(family)}\n\n{data.decode('utf-8').strip()}\n")
        sources.append((f"fonts/OFL.txt ({family})", url, sha))
    (STATIC / "fonts" / "OFL.txt").write_text("\n\n".join(texts))

    tgz_url = f"https://registry.npmjs.org/lucide-static/-/lucide-static-{LUCIDE_VERSION}.tgz"
    data, _ = fetch(tgz_url, LUCIDE_SHA256)
    tar = tarfile.open(fileobj=io.BytesIO(data))
    symbols = []
    for icon in ICONS:
        svg = tar.extractfile(f"package/icons/{icon}.svg").read().decode()
        body = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1)
        body = re.sub(r"<!--.*?-->", "", body, flags=re.S).strip()
        symbols.append(f'  <symbol id="{icon}" viewBox="0 0 24 24">{" ".join(body.split())}</symbol>')
    (STATIC / "icons.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" style="display:none">\n' + "\n".join(symbols) + "\n</svg>\n")
    (STATIC / "LICENSE-lucide.txt").write_text(tar.extractfile("package/LICENSE").read().decode())
    sources.append(("icons.svg, LICENSE-lucide.txt", tgz_url, LUCIDE_SHA256))

    lines = ["# Vendored assets", "", "Fetched and checked by `scripts/vendor_assets.py` (development only).", "",
             "| File | Source | sha256 of the source |", "|---|---|---|"]
    lines += [f"| `{f}` | {u} | `{s}` |" for f, u, s in sources]
    lines += ["", "Fonts: SIL Open Font License 1.1 (`fonts/OFL.txt`), subset to Latin as woff2. "
              "Icons: Lucide, ISC license (`LICENSE-lucide.txt`)."]
    (STATIC / "ASSETS.md").write_text("\n".join(lines) + "\n")
    total = sum(p.stat().st_size for p in STATIC.rglob("*") if p.is_file())
    print(f"wrote {STATIC}: {total / 1024:.0f} KB")


if __name__ == "__main__":
    main()
