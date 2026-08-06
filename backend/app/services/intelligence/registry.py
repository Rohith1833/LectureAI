from typing import Dict, List, Optional
from app.services.intelligence.base import BaseIntelligenceModule


class IntelligenceRegistry:
    """Manages discovery and lifecycle registration of all pluggable intelligence steps."""

    def __init__(self):
        self._modules: Dict[str, BaseIntelligenceModule] = {}

    def register(self, module: BaseIntelligenceModule) -> None:
        """Adds a module to the active registry."""
        self._modules[module.metadata.name] = module

    def unregister(self, name: str) -> Optional[BaseIntelligenceModule]:
        """Removes a module from the active registry."""
        return self._modules.pop(name, None)

    def get_module(self, name: str) -> Optional[BaseIntelligenceModule]:
        """Looks up a module by name."""
        return self._modules.get(name)

    def list_modules(self) -> List[BaseIntelligenceModule]:
        """Returns all currently registered modules."""
        return list(self._modules.values())

    def clear(self) -> None:
        """Resets registry."""
        self._modules.clear()
