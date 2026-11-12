"""Unit tests for the WebUI navigation bar layout and cfg-button callback."""

import unittest

from plantimager.webui.app import setup_web_app
from plantimager.webui.config import update_plantdb_cfg_button
from plantimager.webui.nav import build_navbar_layout


def _walk(component):
    yield component
    children = getattr(component, "children", None)
    if children is component or children is None:
        return
    if isinstance(children, (list, tuple)):
        for child in children:
            if not isinstance(child, str):
                yield from _walk(child)
    elif not isinstance(children, str):
        yield from _walk(children)


class TestCfgButtonCallback(unittest.TestCase):
    def test_returns_children_not_navlink(self):
        from dash_bootstrap_components import NavLink
        result = update_plantdb_cfg_button(True, ["ds1", "ds2"])
        self.assertIsInstance(result, list)
        for item in result:
            self.assertNotIsInstance(item, NavLink)


class TestNavbarLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = setup_web_app("localhost", 5000, "", False, url_prefix="/webui")
        cls.navbar = next(c for c in _walk(cls.app.layout)
                          if type(c).__name__ == "Navbar")

    def test_link_hrefs_carry_prefix(self):
        hrefs = {}
        for c in _walk(self.navbar):
            if getattr(c, "id", None) in ("scan-link", "camera-link", "dataset-table-link"):
                hrefs[c.id] = c.href
        self.assertEqual(hrefs, {
            "scan-link": "/webui/",
            "camera-link": "/webui/cameras",
            "dataset-table-link": "/webui/table",
        })

    def test_logo_src_prefixed_and_brand_not_nested(self):
        logo = next(c for c in _walk(self.navbar) if getattr(c, "id", None) == "navbar-logo")
        self.assertEqual(logo.src, "/webui/assets/logo.svg")
        brand = next(c for c in _walk(self.navbar) if getattr(c, "id", None) == "navbar-brand")
        self.assertEqual(brand.href, "/webui/")

    def test_single_cfg_button(self):
        ids = [getattr(c, "id", None) for c in _walk(self.navbar)]
        self.assertEqual(ids.count("plantdb-cfg-button"), 1)

    def test_no_empty_hrefs(self):
        for c in _walk(self.navbar):
            href = getattr(c, "href", None)
            if href is not None:
                self.assertNotEqual(href, "", f"empty href on {getattr(c, 'id', c)}")


if __name__ == "__main__":
    unittest.main()
