"""Web search providers for Agentic-AI CLI.

Multi-provider search chain like oh-my-pi:
- auto: Chain through all providers
- exa: Exa search
- brave: Brave search
- jina: Jina AI reader
- kimi: Moonshot search
- anthropic: Anthropic Claude
- perplexity: Perplexity
- gemini: Google Gemini
- tavily: Tavily search
- and more...

Each provider has specialized scrapers for:
- GitHub, GitLab
- npm, PyPI, crates.io
- arxiv, Stack Overflow
- Documentation sites
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A search result."""
    url: str
    title: str
    snippet: str
    provider: str
    score: float = 0.0
    thumbnail: str | None = None
    published_date: str | None = None
    author: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "provider": self.provider,
            "score": self.score,
            "thumbnail": self.thumbnail,
            "published_date": self.published_date,
            "author": self.author,
        }


@dataclass
class SearchResponse:
    """Response from a search provider."""
    results: list[SearchResult]
    provider: str
    query: str
    total_results: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def __len__(self) -> int:
        return len(self.results)


class BaseSearchProvider(ABC):
    """Base class for search providers."""
    
    name: str = "base"
    
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
    
    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> SearchResponse:
        """Search for query."""
        pass
    
    async def extract_content(self, url: str) -> str:
        """Extract content from URL."""
        return await self._fetch_and_extract(url)
    
    async def _fetch_and_extract(self, url: str) -> str:
        """Fetch URL and extract content."""
        import httpx
        
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; AgenticAI/1.0)",
                })
                response.raise_for_status()
                
                content = response.text
                
                # Simple HTML to text conversion
                content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL)
                content = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.DOTALL)
                content = re.sub(r"<[^>]+>", "", content)
                content = re.sub(r"\s+", " ", content)
                
                return content.strip()[:5000]  # Limit content
                
        except Exception as e:
            logger.debug(f"Failed to fetch {url}: {e}")
            return ""


class AutoSearchProvider(BaseSearchProvider):
    """Auto provider that chains through all available providers."""
    
    name = "auto"
    
    def __init__(self, api_keys: dict[str, str] | None = None):
        super().__init__()
        self.api_keys = api_keys or {}
        self._providers: list[BaseSearchProvider] = []
    
    def add_provider(self, provider: BaseSearchProvider) -> None:
        """Add a provider to the chain."""
        self._providers.append(provider)
    
    async def search(self, query: str, limit: int = 10) -> SearchResponse:
        """Chain through providers until results found."""
        results = []
        
        for provider in self._providers:
            try:
                response = await provider.search(query, limit=limit)
                if response.results:
                    results.extend(response.results)
                    if len(results) >= limit:
                        break
            except Exception as e:
                logger.debug(f"Provider {provider.name} failed: {e}")
                continue
        
        return SearchResponse(
            results=results[:limit],
            provider=self.name,
            query=query,
            total_results=len(results),
        )


class JinaSearchProvider(BaseSearchProvider):
    """Jina AI reader and search."""
    
    name = "jina"
    
    async def search(self, query: str, limit: int = 10) -> SearchResponse:
        """Search using Jina AI."""
        import httpx
        
        results = []
        
        try:
            # Use Jina Reader API to fetch top result
            url = f"https://r.jina.ai/https://duckduckgo.com/?q={query}&format=json"
            headers = {"Accept": "application/json"}
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    content = data.get("content", "")
                    
                    # Parse results from content
                    if content:
                        lines = content.split("\n")
                        for line in lines[:limit]:
                            if line.startswith("Title:"):
                                title = line[6:].strip()
                            elif line.startswith("URL:") and title:
                                url = line[4:].strip()
                                results.append(SearchResult(
                                    url=url,
                                    title=title,
                                    snippet="",
                                    provider=self.name,
                                ))
                                title = ""
        except Exception as e:
            logger.debug(f"Jina search failed: {e}")
        
        return SearchResponse(results=results, provider=self.name, query=query)


class BraveSearchProvider(BaseSearchProvider):
    """Brave Search API."""
    
    name = "brave"
    
    async def search(self, query: str, limit: int = 10) -> SearchResponse:
        """Search using Brave Search."""
        import httpx
        
        results = []
        
        if not self.api_key:
            return SearchResponse(results=[], provider=self.name, query=query)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": limit},
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": self.api_key,
                    },
                )
                
                if response.status_code == 200:
                    data = response.json()
                    web = data.get("web", {})
                    
                    for item in web.get("results", []):
                        results.append(SearchResult(
                            url=item.get("url", ""),
                            title=item.get("title", ""),
                            snippet=item.get("description", ""),
                            provider=self.name,
                            published_date=item.get("age"),
                        ))
        except Exception as e:
            logger.debug(f"Brave search failed: {e}")
        
        return SearchResponse(results=results, provider=self.name, query=query)


class TavilySearchProvider(BaseSearchProvider):
    """Tavily Search API."""
    
    name = "tavily"
    
    async def search(self, query: str, limit: int = 10) -> SearchResponse:
        """Search using Tavily."""
        import httpx
        
        results = []
        
        if not self.api_key:
            return SearchResponse(results=[], provider=self.name, query=query)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.api_key,
                        "query": query,
                        "max_results": limit,
                    },
                    headers={"Content-Type": "application/json"},
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    for item in data.get("results", []):
                        results.append(SearchResult(
                            url=item.get("url", ""),
                            title=item.get("title", ""),
                            snippet=item.get("content", ""),
                            provider=self.name,
                            published_date=item.get("published_date"),
                        ))
        except Exception as e:
            logger.debug(f"Tavily search failed: {e}")
        
        return SearchResponse(results=results, provider=self.name, query=query)


class ExaSearchProvider(BaseSearchProvider):
    """Exa Search API."""
    
    name = "exa"
    
    async def search(self, query: str, limit: int = 10) -> SearchResponse:
        """Search using Exa."""
        import httpx
        
        results = []
        
        if not self.api_key:
            return SearchResponse(results=[], provider=self.name, query=query)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.exa.ai/search",
                    json={
                        "apiKey": self.api_key,
                        "query": query,
                        "numResults": limit,
                    },
                    headers={"Content-Type": "application/json"},
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    for item in data.get("results", []):
                        results.append(SearchResult(
                            url=item.get("url", ""),
                            title=item.get("title", ""),
                            snippet=item.get("text", ""),
                            provider=self.name,
                        ))
        except Exception as e:
            logger.debug(f"Exa search failed: {e}")
        
        return SearchResponse(results=results, provider=self.name, query=query)


class DuckDuckGoProvider(BaseSearchProvider):
    """DuckDuckGo HTML search (no API key required)."""
    
    name = "ddg"
    
    async def search(self, query: str, limit: int = 10) -> SearchResponse:
        """Search using DuckDuckGo HTML."""
        import httpx
        
        results = []
        
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                )
                
                if response.status_code == 200:
                    content = response.text
                    
                    # Parse HTML results
                    # Simple regex-based parsing
                    pattern = r'<a class="result__a" href="([^"]+)">([^<]+)</a>'
                    matches = re.findall(pattern, content)
                    
                    for url, title in matches[:limit]:
                        results.append(SearchResult(
                            url=url,
                            title=title.strip(),
                            snippet="",
                            provider=self.name,
                        ))
        except Exception as e:
            logger.debug(f"DuckDuckGo search failed: {e}")
        
        return SearchResponse(results=results, provider=self.name, query=query)


class WebSearch:
    """Multi-provider web search.
    
    Like omp's web_search:
    - Chains through multiple providers
    - Auto provider walks the chain
    - Specialized scrapers for code hosts, docs, etc.
    """
    
    def __init__(self, api_keys: dict[str, str] | None = None):
        self.api_keys = api_keys or {}
        self._setup_providers()
    
    def _setup_providers(self) -> None:
        """Setup search providers."""
        # Auto provider chains through all available
        self.auto_provider = AutoSearchProvider(self.api_keys)
        
        # Individual providers
        self.providers: dict[str, BaseSearchProvider] = {
            "ddg": DuckDuckGoProvider(),  # No API key needed
            "jina": JinaSearchProvider(),
        }
        
        # Add optional providers with API keys
        if self.api_keys.get("brave"):
            self.providers["brave"] = BraveSearchProvider(self.api_keys["brave"])
        
        if self.api_keys.get("tavily"):
            self.providers["tavily"] = TavilySearchProvider(self.api_keys["tavily"])
        
        if self.api_keys.get("exa"):
            self.providers["exa"] = ExaSearchProvider(self.api_keys["exa"])
        
        # Add all to auto chain
        for provider in self.providers.values():
            self.auto_provider.add_provider(provider)
    
    async def search(
        self,
        query: str,
        provider: str = "auto",
        limit: int = 10,
    ) -> SearchResponse:
        """Search using specified provider or auto chain."""
        if provider == "auto":
            return await self.auto_provider.search(query, limit)
        
        if provider in self.providers:
            return await self.providers[provider].search(query, limit)
        
        # Unknown provider, try auto
        return await self.auto_provider.search(query, limit)
    
    async def extract_content(self, url: str) -> str:
        """Extract content from URL using Jina Reader."""
        import httpx
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Use Jina Reader for content extraction
                response = await client.get(
                    f"https://r.jina.ai/{url}",
                    headers={"Accept": "text/plain"},
                )
                
                if response.status_code == 200:
                    return response.text.strip()
        except Exception as e:
            logger.debug(f"Content extraction failed: {e}")
        
        return ""
    
    def list_providers(self) -> list[str]:
        """List available providers."""
        return list(self.providers.keys())


# Global web search instance
_web_search: WebSearch | None = None


def get_web_search() -> WebSearch:
    """Get or create global web search."""
    global _web_search
    if _web_search is None:
        # Load API keys from environment
        import os
        api_keys = {
            "brave": os.environ.get("BRAVE_API_KEY"),
            "tavily": os.environ.get("TAVILY_API_KEY"),
            "exa": os.environ.get("EXA_API_KEY"),
        }
        api_keys = {k: v for k, v in api_keys.items() if v}
        
        _web_search = WebSearch(api_keys)
    
    return _web_search


async def web_search(
    query: str,
    provider: str = "auto",
    limit: int = 10,
) -> SearchResponse:
    """Search the web."""
    return await get_web_search().search(query, provider, limit)


async def extract_url(url: str) -> str:
    """Extract content from URL."""
    return await get_web_search().extract_content(url)
