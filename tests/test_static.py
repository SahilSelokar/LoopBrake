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
        assert url.startswith(("/static/", "#")), url  # "#refract" is the page's own SVG filter


def test_every_icon_used_exists():
    sprite = set(re.findall(r'<symbol id="([a-z0-9-]+)"', read("icons.svg")))
    js = read("app.js")
    used = set(re.findall(r"icons\.svg#([a-z0-9-]+)", read("index.html")))
    used |= set(re.findall(r'icon\("([a-z0-9-]+)"\)', js))
    tools = js[js.index("const TOOLS = {"):js.index("const SYMPTOMS")]  # TOOLS and STATES: [words, icon, ...]
    used |= set(re.findall(r'\["[^"]+", "([a-z0-9-]+)"', tools))
    how = js[js.index("  how: ["):js.index("  wordsTitle:")]  # [icon, title, text]
    used |= set(re.findall(r'\["([a-z0-9-]+)", "[A-Z]', how))
    used |= set(re.findall(r'server \? "([a-z0-9-]+)" : "([a-z0-9-]+)"', js)[0])
    assert {"square-terminal", "file-text", "gauge", "plug", "loader-circle"} <= used and used <= sprite, used - sprite


def test_no_inline_style_attributes():
    """The CSP allows styles only from app.css, so a style="" attribute would be silently dropped.
    Setting el.style.x from code is fine: that's the CSS object model, which the CSP allows."""
    assert not re.search(r'\bstyle: "', read("app.js")) and "style=" not in read("index.html")


def test_red_is_only_a_fill():
    css = read("app.css")
    assert not re.search(r"(?<![-\w])color:\s*var\(--red\)", css)
    assert "fill: var(--red)" in css or "background: var(--red)" in css


def _themes(css):
    """{token: (light hex, dark hex)} from the `--name: light-dark(#light, #dark)` pairs."""
    return {n: (a, b) for n, a, b in re.findall(r"--([a-z0-9]+):\s*light-dark\((#[0-9A-Fa-f]{6}),\s*(#[0-9A-Fa-f]{6})\)", css)}


def _hex(css, name):
    return re.search(rf"--{name}:\s*(#[0-9A-Fa-f]{{6}})", css).group(1)


def _luminance(hexcolor):
    rgb = [int(hexcolor[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_text_colors_pass_wcag_aa_in_both_themes():
    css = read("app.css")
    themes = _themes(css)
    pairs = [("text", bg) for bg in ("bg", "panel", "panel2", "redtint", "greentint", "limetint")]
    pairs += [("muted", bg) for bg in ("bg", "panel", "panel2")] + [("accent", bg) for bg in ("bg", "panel", "panel2")]
    pairs += [("navtext", "navbg")]
    for i, theme in enumerate(("light", "dark")):
        for fg, bg in pairs:
            ratio = contrast(themes[fg][i], themes[bg][i])
            assert ratio >= 4.5, (theme, fg, bg, round(ratio, 2))
        assert contrast(_hex(css, "red"), themes["panel"][i]) >= 3  # red as a fill (non-text) is visible
    brand = {n: _hex(css, n) for n in ("night", "lime", "red", "ink", "paper")}
    assert contrast(brand["ink"], brand["lime"]) >= 4.5  # buttons: ink on lime, in both themes
    assert contrast(brand["red"], brand["night"]) < 4.5  # why red is never text (constitution)
    assert contrast(brand["ink"], brand["red"]) >= 3  # the icon on its red circle: non-text, 3:1 is enough
    assert themes["accent"][0] != brand["lime"]  # on light backgrounds lime is a fill only, never text


def test_size_budget():
    assert sum(p.stat().st_size for p in STATIC.rglob("*") if p.is_file()) < 400 * 1024


def test_plain_words_on_screen():
    js = read("app.js")
    text_block = js[js.index("const TEXT = {"):js.index("};", js.index("const TEXT = {"))]
    shown = text_block + "".join(dashboard.LABELS.values()) + dashboard.NEXT_STEP
    shown += claude_code.plain_stop(7, 6, 40, 0.05, "past the stop line; repeating in 5 of last 5 steps", dashboard.NEXT_STEP)
    for word in ("τ", "α", " kill", "score", "step ", " run id"):
        assert word not in shown, word
