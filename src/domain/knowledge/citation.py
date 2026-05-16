"""Citation domain module."""


class Citation:
    """Represents a citation from evidence."""
    
    def __init__(self, source: str, page: int, text: str):
        self.source = source
        self.page = page
        self.text = text
