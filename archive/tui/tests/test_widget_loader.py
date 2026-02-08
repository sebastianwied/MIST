"""Tests for widget_loader (unit tests, no broker needed)."""

from __future__ import annotations

import pytest

from mist_tui.widget_base import BrokerWidget
from mist_tui.widget_loader import WidgetSpec, load_widget_class, parse_widget_specs


def test_parse_widget_specs_extracts_specs():
    """parse_widget_specs returns WidgetSpec list from manifest."""
    manifest = {
        "name": "test-agent",
        "widgets": [
            {
                "id": "chat",
                "module": "mist_tui.widgets.chat",
                "class_name": "ChatPanel",
                "default": True,
            },
            {
                "id": "status",
                "module": "some.module",
                "class_name": "StatusWidget",
            },
        ],
    }
    specs = parse_widget_specs(manifest)
    assert len(specs) == 2
    assert specs[0] == WidgetSpec(
        id="chat", module="mist_tui.widgets.chat",
        class_name="ChatPanel", default=True,
    )
    assert specs[1] == WidgetSpec(
        id="status", module="some.module",
        class_name="StatusWidget", default=False,
    )


def test_parse_widget_specs_empty_manifest():
    """Empty or missing widgets key returns empty list."""
    assert parse_widget_specs({}) == []
    assert parse_widget_specs({"widgets": []}) == []
    assert parse_widget_specs({"widgets": "not a list"}) == []


def test_parse_widget_specs_skips_incomplete():
    """Incomplete widget entries are skipped."""
    manifest = {
        "widgets": [
            {"id": "x"},  # missing module, class_name
            {"id": "y", "module": "m"},  # missing class_name
            {"id": "z", "module": "m", "class_name": "C"},  # OK
        ],
    }
    specs = parse_widget_specs(manifest)
    assert len(specs) == 1
    assert specs[0].id == "z"


def test_load_widget_class_builtin():
    """load_widget_class loads the built-in ChatPanel."""
    spec = WidgetSpec(
        id="chat", module="mist_tui.widgets.chat", class_name="ChatPanel",
    )
    cls = load_widget_class(spec)
    assert cls is not None
    assert issubclass(cls, BrokerWidget)


def test_load_widget_class_missing_module():
    """Missing module returns None."""
    spec = WidgetSpec(
        id="x", module="nonexistent.module.xyz", class_name="Foo",
    )
    cls = load_widget_class(spec)
    assert cls is None


def test_load_widget_class_missing_class():
    """Module exists but class doesn't → returns None."""
    spec = WidgetSpec(
        id="x", module="mist_tui.widgets.chat", class_name="DoesNotExist",
    )
    cls = load_widget_class(spec)
    assert cls is None


def test_load_widget_class_not_broker_widget():
    """Class that isn't a BrokerWidget subclass → returns None."""
    spec = WidgetSpec(
        id="x", module="mist_tui.widget_loader", class_name="WidgetSpec",
    )
    cls = load_widget_class(spec)
    assert cls is None


# ── MIST-specific widget loading tests ──────────────────────────────
# These require mist-agent to be installed; skipped otherwise.

mist_agent = pytest.importorskip("mist_agent")


def test_load_mist_chat_panel():
    """MistChatPanel loads from mist_agent.widgets.chat."""
    spec = WidgetSpec(
        id="chat",
        module="mist_agent.widgets.chat",
        class_name="MistChatPanel",
        default=True,
    )
    cls = load_widget_class(spec)
    assert cls is not None
    assert issubclass(cls, BrokerWidget)
    assert cls.__name__ == "MistChatPanel"


def test_load_mist_topics_panel():
    """TopicsPanel loads from mist_agent.widgets.topics."""
    spec = WidgetSpec(
        id="topics",
        module="mist_agent.widgets.topics",
        class_name="TopicsPanel",
    )
    cls = load_widget_class(spec)
    assert cls is not None
    assert issubclass(cls, BrokerWidget)
    assert cls.__name__ == "TopicsPanel"


def test_parse_mist_manifest_widgets():
    """parse_widget_specs works with the MIST agent manifest."""
    from mist_agent.manifest import MANIFEST

    specs = parse_widget_specs(MANIFEST)
    assert len(specs) == 2
    assert specs[0].id == "chat"
    assert specs[0].module == "mist_agent.widgets.chat"
    assert specs[0].class_name == "MistChatPanel"
    assert specs[0].default is True
    assert specs[1].id == "topics"
    assert specs[1].module == "mist_agent.widgets.topics"
    assert specs[1].class_name == "TopicsPanel"


def test_tui_falls_back_when_no_widgets():
    """Catalog entry without widgets → parse_widget_specs returns empty."""
    catalog_entry = {
        "agent_id": "echo-0",
        "name": "echo",
        "commands": ["echo"],
        "description": "Echo agent",
    }
    specs = parse_widget_specs(catalog_entry)
    assert specs == []


def test_tui_falls_back_on_import_failure():
    """Widget with bad module path → load_widget_class returns None."""
    spec = WidgetSpec(
        id="chat",
        module="mist_agent.widgets.nonexistent",
        class_name="MistChatPanel",
    )
    cls = load_widget_class(spec)
    assert cls is None
