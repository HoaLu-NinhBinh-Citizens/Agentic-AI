"""Web search integration for Agentic-AI.

Provides:
- Multiple search providers (Tavily, DuckDuckGo, Google)
- Web scraping
- Content extraction
- Search result ranking
- Caching
"""

from __future__ import annotations

import asyncio
import html
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import quote_plus, urlencode
from uuid import uuid4

import httpx


class SearchProvider(Enum):
    """Available search providers."""
    DUCKDUCKGO = "duckduckgo"
    TAVILY = "tavily"
    SERPAPI = "serpapi"
    BRAVE = "brave"


@dataclass
class SearchResult:
    """A search result."""
    title: str
    url: str
    snippet: str
    source: str = ""
    score: float = 0.0
    published_date: str | None = None


@dataclass
class SearchResponse:
    """Response from search."""
    query: str
    results: list[SearchResult]
    total_results: int = 0
    provider: str = ""
    cached: bool = False


class SearchCache:
    """Cache for search results."""
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self._cache: dict[str, tuple[SearchResponse, float]] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds
    
    def _make_key(self, query: str, provider: str) -> str:
        return f"{provider}:{query.lower().strip()}"
    
    def get(self, query: str, provider: str) -> SearchResponse | None:
        """Get cached result."""
        key = self._make_key(query, provider)
        if key in self._cache:
            result, timestamp = self._cache[key]
            import time
            if time.time() - timestamp < self._ttl:
                result.cached = True
                return result
            del self._cache[key]
        return None
    
    def set(self, query: str, provider: str, response: SearchResponse) -> None:
        """Cache a result."""
        key = self._make_key(query, provider)
        import time
        self._cache[key] = (response, time.time())
        
        # Evict if too large
        if len(self._cache) > self._max_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]


class DuckDuckGoSearch:
    """DuckDuckGo search without API key."""
    
    def __init__(self):
        self.base_url = "https://duckduckgo.com/html/"
    
    async def search(
        self,
        query: str,
        num_results: int = 10,
    ) -> list[SearchResult]:
        """Search DuckDuckGo."""
        params = {
            "q": query,
            "kl": "wt-wt",
        }
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(self.base_url, params=params)
            
            return self._parse_html(response.text)
    
    def _parse_html(self, html_content: str) -> list[SearchResult]:
        """Parse DuckDuckGo HTML results."""
        results = []
        
        # Find result blocks
        pattern = r'<a class="result__a" href="([^"]+)">([^<]+)</a>'
        matches = re.findall(pattern, html_content)
        
        pattern_snippet = r'<a class="result__a" href="[^"]+">[^<]+</a></h2>\s*<p class="result__snippet">([^<]+)</p>'
        snippets = re.findall(pattern_snippet, html_content)
        
        for i, (url, title) in enumerate(matches[:10]):
            snippet = snippets[i] if i < len(snippets) else ""
            snippet = html.unescape(snippet).strip()
            
            results.append(SearchResult(
                title=html.unescape(title).strip(),
                url=url,
                snippet=snippet,
                source="duckduckgo",
            ))
        
        return results


class TavilySearch:
    """Tavily AI search API."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.tavily.com/search"
    
    async def search(
        self,
        query: str,
        num_results: int = 10,
        include_answer: bool = False,
        include_raw_content: bool = False,
    ) -> SearchResponse:
        """Search using Tavily API."""
        params = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": num_results,
            "include_answer": include_answer,
            "include_raw_content": include_raw_content,
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.base_url, json=params)
            response.raise_for_status()
            
            data = response.json()
            
            results = [
                SearchResult(
                    title=r["title"],
                    url=r["url"],
                    snippet=r.get("content", ""),
                    score=r.get("score", 0),
                )
                for r in data.get("results", [])
            ]
            
            return SearchResponse(
                query=query,
                results=results,
                total_results=data.get("total_results", len(results)),
                provider="tavily",
            )


class SerpAPISearch:
    """Google search via SerpAPI."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://serpapi.com/search"
    
    async def search(
        self,
        query: str,
        num_results: int = 10,
        engine: str = "google",
    ) -> list[SearchResult]:
        """Search via SerpAPI."""
        params = {
            "q": query,
            "api_key": self.api_key,
            "num": num_results,
            "engine": engine,
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(self.base_url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            results = []
            for r in data.get("organic_results", [])[:num_results]:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("link", ""),
                    snippet=r.get("snippet", ""),
                    score=r.get("position", 0) / num_results,
                ))
            
            return results


class BraveSearch:
    """Brave Search API."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.search.brave.com/res/v1/web/search"
    
    async def search(
        self,
        query: str,
        num_results: int = 10,
    ) -> list[SearchResult]:
        """Search using Brave."""
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        
        params = {
            "q": query,
            "count": num_results,
        }
        
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            response = await client.get(self.base_url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            results = []
            for r in data.get("web", {}).get("results", {}).get("results", [])[:num_results]:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("description", ""),
                ))
            
            return results


class WebScraper:
    """Web content scraper."""
    
    def __init__(self):
        self._client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; Agentic-AI/1.0)",
                },
            )
        return self._client
    
    async def scrape(
        self,
        url: str,
        selectors: list[str] | None = None,
    ) -> str:
        """Scrape content from URL."""
        client = await self._get_client()
        
        response = await client.get(url)
        response.raise_for_status()
        
        content = response.text
        
        # Extract main content
        if selectors:
            for selector in selectors:
                content = self._extract_selector(content, selector)
        
        # Clean content
        content = self._clean_html(content)
        
        return content
    
    def _extract_selector(self, html: str, selector: str) -> str:
        """Extract content matching selector."""
        # Simple CSS-like selector support
        if selector.startswith("."):
            # Class selector
            pattern = rf'<[^>]*class="[^"]*{selector[1:]}[^"]*"[^>]*>(.*?)</[^>]+>'
        elif selector.startswith("#"):
            # ID selector
            pattern = rf'<[^>]*id="{selector[1:]}"[^>]*>(.*?)</[^>]+>'
        else:
            # Tag selector
            pattern = rf'<{selector}[^>]*>(.*?)</{selector}>'
        
        matches = re.findall(pattern, html, re.DOTALL)
        return " ".join(matches)
    
    def _clean_html(self, html: str) -> str:
        """Clean HTML to plain text."""
        # Remove scripts and styles
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
        
        # Remove HTML tags
        html = re.sub(r'<[^>]+>', ' ', html)
        
        # Decode entities
        html = html.unescape() if hasattr(html, 'unescape') else html
        
        # Clean whitespace
        html = re.sub(r'\s+', ' ', html)
        
        return html.strip()


class WebSearchManager:
    """Manages multiple search providers."""
    
    def __init__(self):
        self._providers: dict[SearchProvider, Any] = {}
        self._cache = SearchCache()
        self._scraper = WebScraper()
    
    def register_provider(self, provider: SearchProvider, instance: Any) -> None:
        """Register a search provider."""
        self._providers[provider] = instance
    
    async def search(
        self,
        query: str,
        provider: SearchProvider = SearchProvider.DUCKDUCKGO,
        num_results: int = 10,
        use_cache: bool = True,
    ) -> SearchResponse:
        """Search using specified provider."""
        # Check cache
        if use_cache:
            cached = self._cache.get(query, provider.value)
            if cached:
                return cached
        
        # Get provider
        if provider == SearchProvider.DUCKDUCKGO:
            provider_instance = self._providers.get(provider)
            if not provider_instance:
                provider_instance = DuckDuckGoSearch()
                self._providers[provider] = provider_instance
            
            results = await provider_instance.search(query, num_results)
            response = SearchResponse(
                query=query,
                results=results,
                provider=provider.value,
            )
        else:
            # Other providers need API keys
            provider_instance = self._providers.get(provider)
            if not provider_instance:
                raise ValueError(f"Provider {provider.value} not configured")
            
            result = await provider_instance.search(query, num_results)
            response = result if isinstance(result, SearchResponse) else SearchResponse(
                query=query,
                results=result,
                provider=provider.value,
            )
        
        # Cache result
        if use_cache:
            self._cache.set(query, provider.value, response)
        
        return response
    
    async def scrape_url(self, url: str) -> str:
        """Scrape content from URL."""
        return await self._scraper.scrape(url)
    
    async def search_and_scrape(
        self,
        query: str,
        num_results: int = 5,
    ) -> list[dict]:
        """Search and scrape top results."""
        results = await self.search(query, num_results=num_results)
        
        scraped = []
        for result in results.results[:num_results]:
            try:
                content = await self.scrape_url(result.url)
                scraped.append({
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet,
                    "content": content[:5000],  # Limit content
                })
            except Exception:
                scraped.append({
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet,
                    "content": None,
                })
        
        return scraped


# Convenience functions

async def quick_search(query: str, provider: str = "duckduckgo") -> SearchResponse:
    """Quick search without setup."""
    manager = WebSearchManager()
    
    provider_enum = SearchProvider(provider.lower())
    return await manager.search(query, provider_enum)


async def search_and_research(query: str, num_results: int = 10) -> list[dict]:
    """Search and scrape multiple sources."""
    manager = WebSearchManager()
    return await manager.search_and_scrape(query, num_results)
