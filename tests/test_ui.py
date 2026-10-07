"""Check the composed document, including assets behind a reverse proxy."""
from collections import Counter
from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.ids, self.references, self.assets = [], [], []
        self.feed(source)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        for name in ("for", "aria-labelledby", "aria-controls"):
            self.references.extend(attrs.get(name, "").split())
        if tag == "script" and attrs.get("src"):
            self.assets.append(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.assets.append(attrs["href"])


@pytest.mark.parametrize("prefix", ["", "/projects/mailaya"])
def test_composed_ui_references_and_assets_are_valid(api_app, prefix):
    with TestClient(api_app.app, root_path=prefix, base_url="https://lab.example") as client:
        page = client.get(prefix + "/")
        assert page.status_code == 200
        assert "__TRIAGE__" not in page.text and "__WORKSPACE_SETTINGS__" not in page.text
        document = Document(page.text)
        assert not [name for name, count in Counter(document.ids).items() if count > 1]
        assert set(document.references) <= set(document.ids)
        assert document.assets
        for asset in document.assets:
            assert urlsplit(asset).path.startswith(prefix + "/static/")
            assert not urlsplit(asset).netloc  # UI has no external font or script dependency.
            response = client.get(asset)
            assert response.status_code == 200
            assert response.content
        guide = client.get(prefix + "/guide")
        assert guide.status_code == 200
        assert "Fonctions par boîte" in guide.text and "Recherche en langage naturel" in guide.text
