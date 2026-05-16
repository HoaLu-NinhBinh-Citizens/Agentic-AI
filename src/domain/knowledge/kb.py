"""Knowledge base domain module."""


class KnowledgeBase:
    """Knowledge base for citations."""
    
    def __init__(self):
        self.entries: list[dict] = []
    
    def add_entry(self, key: str, value: dict) -> None:
        """Add entry to knowledge base."""
        self.entries.append({"key": key, "value": value})
    
    def query(self, key: str) -> list[dict]:
        """Query knowledge base."""
        return [e for e in self.entries if e.get("key") == key]
