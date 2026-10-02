"""The dashboard's page files: brand rules, accessibility basics and plain words (contracts/ui.md)."""
import re
from pathlib import Path

from loopbrake import claude_code, dashboard

STATIC = Path(dashboard.__file__).parent / "static"
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
TEXT_FILES = [p for p in STATIC.rglob("*") if p.suffix in (".html", ".css", ".js", ".svg", ".md", ".txt")]
SVG_NS = "http://www.w3.org/2000/svg"
LICENSE_FILES = {"OFL.txt", "LICENSE-lucide.txt", "ASSETS.md"}


def read(name):
    return (STATIC / name).read_text(encoding="utf-8")


def test_no_emoji_anywhere():
    for p in TEXT_FILES:
        assert not EMOJI.search(p.read_text(encoding="utf-8")), p.name


def test_nothing_loads_from_the_internet():
    for p in TEXT_FILES:
        if p.name in LICENSE_FILES:
            continue
        text = p.read_text(encoding="utf-8")
        if p.name == "app.js":  # the copyable setup lines are text people copy; nothing loads them
            text = text[:text.index("const SETUP = [")] + text[text.index("];", text.index("const SETUP = [")):]
        urls = [u for u in re.findall(r"https?://[^\s\"')]+", text) if u != SVG_NS]
        assert not urls, (p.name, urls)
    for url in re.findall(r"url\(\s*\"?([^\")]+)", read("app.css")):
        assert url.startswith("/static/"), url


def test_every_icon_used_exists():
    sprite = set(re.findall(r'<symbol id="([a-z0-9-]+)"', read("icons.svg")))
    used = set(re.findall(r"icons\.svg#([a-z0-9-]+)", read("index.html")))
    used |= set(re.findall(r'icon\("([a-z0-9-]+)"\)', read("app.js")))
    assert used and used <= sprite, used - sprite


def test_red_is_only_a_fill():
    css = read("app.css")
    assert not re.search(r"(?<![-\w])color:\s*var\(--red\)", css)
    assert "fill: var(--red)" in css or "background: var(--red)" in css


def _hex(css, name):
    return re.search(rf"--{name}:\s*(#[0-9A-Fa-f]{{6}})", css).group(1)


def _luminance(hexcolor):
    rgb = [int(hexcolor[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_text_colors_pass_wcag_aa():
    css = read("app.css")
    c = {n: _hex(css, n) for n in ("night", "lime", "green", "red", "redtint", "paper", "ink", "panel", "muted")}
    pairs = [("paper", "night"), ("paper", "panel"), ("muted", "panel"), ("muted", "night"), ("lime", "night"),
             ("lime", "panel"), ("ink", "lime"), ("paper", "redtint"), ("paper", "green")]
    for fg, bg in pairs:
        assert contrast(c[fg], c[bg]) >= 4.5, (fg, bg, round(contrast(c[fg], c[bg]), 2))
    assert contrast(c["red"], c["night"]) < 4.5  # why red is never text (constitution)
    assert contrast(c["ink"], c["red"]) >= 3  # the icon on its red circle: non-text, 3:1 is enough


def test_size_budget():
    assert sum(p.stat().st_size for p in STATIC.rglob("*") if p.is_file()) < 400 * 1024


def test_plain_words_on_screen():
    js = read("app.js")
    text_block = js[js.index("const TEXT = {"):js.index("};", js.index("const TEXT = {"))]
    shown = text_block + "".join(dashboard.LABELS.values()) + dashboard.NEXT_STEP
    shown += claude_code.plain_stop(7, 6, 40, 0.05, "past the stop line; repeating in 5 of last 5 steps", dashboard.NEXT_STEP)
    for word in ("τ", "α", " kill", "score", "step ", " run id"):
        assert word not in shown, word
