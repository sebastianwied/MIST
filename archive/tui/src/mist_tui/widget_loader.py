"""Dynamic widget loading from agent manifests."""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any

from .widget_base import BrokerWidget

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WidgetSpec:
    """Describes a widget to load from a manifest."""

    id: str
    module: str
    class_name: str
    default: bool = False


def parse_widget_specs(manifest: dict[str, Any]) -> list[WidgetSpec]:
    """Extract widget specs from an agent manifest dict.

    Expects a ``"widgets"`` key containing a list of dicts with
    ``id``, ``module``, ``class_name``, and optional ``default``.
    """
    raw = manifest.get("widgets", [])
    if not isinstance(raw, list):
        return []
    specs: list[WidgetSpec] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        wid = entry.get("id")
        module = entry.get("module")
        class_name = entry.get("class_name")
        if not all((wid, module, class_name)):
            log.warning("skipping incomplete widget spec: %s", entry)
            continue
        specs.append(WidgetSpec(
            id=wid,
            module=module,
            class_name=class_name,
            default=bool(entry.get("default", False)),
        ))
    return specs


def load_widget_class(spec: WidgetSpec) -> type[BrokerWidget] | None:
    """Import a widget class from a spec.

    Returns ``None`` (with a log warning) if the module cannot be
    imported or the class is not a ``BrokerWidget`` subclass.
    """
    try:
        mod = importlib.import_module(spec.module)
    except ImportError:
        log.warning("cannot import widget module %r", spec.module)
        return None

    cls = getattr(mod, spec.class_name, None)
    if cls is None:
        log.warning(
            "class %r not found in module %r", spec.class_name, spec.module,
        )
        return None

    if not (isinstance(cls, type) and issubclass(cls, BrokerWidget)):
        log.warning(
            "%r.%r is not a BrokerWidget subclass",
            spec.module, spec.class_name,
        )
        return None

    return cls
