from __future__ import annotations

from core.plantuml_common import PLANTUML_HEADER
from core.schemas import CanonicalRegistry


def render_canonical_registry_to_plantuml(registry: CanonicalRegistry) -> str:
    lines = PLANTUML_HEADER.copy()
    for entity in registry.entities:
        lines.append(f"class {entity.name} {{")
        if entity.aliases:
            aliases = ", ".join(entity.aliases[:4])
            lines.append(f"  .. aliases: {aliases} ..")
        lines.append("}")
        lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


__all__ = ["render_canonical_registry_to_plantuml"]
