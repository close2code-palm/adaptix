from abc import ABC
from typing import Dict, Optional


class ContextNamespace(ABC):
    def add(self, name: str, value: object) -> None:
        pass


class BuiltinContextNamespace(ContextNamespace):
    def __init__(self, namespace: Optional[Dict[str, object]] = None):
        if namespace is None:
            namespace = {}

        self.dict = namespace

    def add(self, name: str, value: object) -> None:
        if name in self.dict:
            raise KeyError("Key duplication")

        self.dict[name] = value