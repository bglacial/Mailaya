"""Build the shipped, dependency-free HTML help from USER_GUIDE.md."""
from pathlib import Path
import html
import re

ROOT = Path(__file__).resolve().parents[1]


def inline(value):
    value = html.escape(value)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    return re.sub(r"\[([^\]]+)\]\((https?://[^ )]+)\)", r'<a href="\2">\1</a>', value)


def render(source):
    result, paragraph = [], []
    in_code = False
    list_type = None
    def flush():
        if paragraph:
            result.append("<p>" + inline(" ".join(paragraph)) + "</p>")
            paragraph.clear()
    def close_list():
        nonlocal list_type
        if list_type:
            result.append(f"</{list_type}>")
            list_type = None
    for line in source.splitlines():
        if line.startswith("```"):
            flush(); close_list()
            result.append("</code></pre>" if in_code else "<pre><code>")
            in_code = not in_code
            continue
        if in_code:
            result.append(html.escape(line))
            continue
        if not line.strip():
            flush(); close_list(); continue
        heading = re.match(r"^(#{1,4}) (.*)", line)
        if heading:
            flush(); close_list()
            level = len(heading[1]); label = heading[2]
            anchor = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
            result.append(f'<h{level} id="{anchor}">{inline(label)}</h{level}>')
            continue
        bullet = re.match(r"^(?:- |\d+\. )(.*)", line)
        if bullet:
            flush()
            kind = "ul" if line.startswith("- ") else "ol"
            if list_type != kind:
                close_list(); list_type = kind; result.append(f"<{kind}>")
            result.append("<li>" + inline(bullet[1]) + "</li>")
            continue
        close_list(); paragraph.append(line)
    flush(); close_list()
    return "\n".join(result)


def main():
    source = (ROOT / "USER_GUIDE.md").read_text()
    headings = re.findall(r"^## (.*)$", source, re.M)
    links = "".join(f'<li><a href="#{re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")}">{inline(label)}</a></li>' for label in headings)
    page = '<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' \
           '<title>Guide Mailaya</title><link rel="stylesheet" href="__MAILAYA_ROOT__/static/app.css?v=workspace-9"></head>' \
           '<body class="guide-page"><nav><a href="__MAILAYA_ROOT__/">← Revenir à Mailaya</a></nav><article>' \
           '<details open><summary>Sommaire du guide</summary><ol>' + links + '</ol></details>' + render(source) + '</article></body></html>'
    (ROOT / "app/static/guide.html").write_text(page)
    print("Guide HTML régénéré depuis USER_GUIDE.md.")


if __name__ == "__main__":
    main()
