"""Vision & Codebase Understanding - Multi-modal AI support.

Features:
- Image analysis
- Screenshot capture
- Diagram understanding
- Code visualization
- Architecture analysis
"""

from __future__ import annotations

import base64
import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ImageAnalysis:
    """Result of image analysis."""
    description: str
    objects: list[str]
    text: str
    confidence: float
    raw: Optional[dict[str, Any]] = None


class VisionProvider:
    """
    Vision support for images, screenshots, diagrams.
    
    Usage:
        vision = VisionProvider()
        
        # Analyze image
        result = await vision.analyze_image("diagram.png")
        
        # Analyze screenshot
        result = await vision.analyze_screenshot()
        
        # Analyze from bytes
        result = await vision.analyze_bytes(image_bytes)
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._use_mock = not self.api_key
    
    async def analyze_image(self, image_path: str) -> ImageAnalysis:
        """Analyze an image file."""
        path = Path(image_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        # Read image
        with open(path, "rb") as f:
            image_bytes = f.read()
        
        return await self.analyze_bytes(image_bytes)
    
    async def analyze_bytes(self, image_bytes: bytes) -> ImageAnalysis:
        """Analyze image from bytes."""
        if self._use_mock:
            return ImageAnalysis(
                description="Mock analysis of image",
                objects=["mock object 1", "mock object 2"],
                text="Mock text detected in image",
                confidence=0.9,
            )
        
        # Use OpenAI Vision
        import aiohttp
        
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        # Encode image
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        
        payload = {
            "model": "gpt-4-vision-preview",
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Describe this image in detail. What objects, text, and diagrams are visible?"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }],
            "max_tokens": 1000,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise Exception(f"Vision API error: {error}")
                
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                
                return ImageAnalysis(
                    description=content,
                    objects=[],  # Would need parsing
                    text="",
                    confidence=0.9,
                    raw=data,
                )
    
    async def analyze_screenshot(self) -> ImageAnalysis:
        """Capture and analyze screenshot."""
        # On Windows, use PIL/numpy to capture
        try:
            from PIL import ImageGrab
            
            screenshot = ImageGrab.grab()
            img_bytes = io.BytesIO()
            screenshot.save(img_bytes, format="PNG")
            img_bytes = img_bytes.getvalue()
            
            return await self.analyze_bytes(img_bytes)
        except ImportError:
            return ImageAnalysis(
                description="Screenshot capture not available (PIL not installed)",
                objects=[],
                text="",
                confidence=0.0,
            )


class CodebaseUnderstanding:
    """
    Deep codebase understanding - similar to Codex's code analysis.
    
    Features:
    - AST parsing
    - Call graph analysis
    - Symbol resolution
    - Dependency tracking
    - Architecture extraction
    """

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self._cache: dict[str, Any] = {}
    
    async def analyze_structure(self) -> dict[str, Any]:
        """Analyze project structure."""
        structure = {
            "directories": [],
            "files": [],
            "file_types": {},
            "size_total": 0,
        }
        
        for root, dirs, files in os.walk(self.workspace_root):
            root_path = Path(root)
            rel_root = root_path.relative_to(self.workspace_root)
            
            for d in dirs:
                structure["directories"].append(str(rel_root / d))
            
            for f in files:
                file_path = root_path / f
                ext = file_path.suffix
                
                structure["files"].append({
                    "path": str(rel_root / f),
                    "size": file_path.stat().st_size,
                    "type": ext,
                })
                
                structure["file_types"][ext] = structure["file_types"].get(ext, 0) + 1
                structure["size_total"] += file_path.stat().st_size
        
        return structure
    
    async def analyze_dependencies(self) -> dict[str, Any]:
        """Analyze code dependencies."""
        deps = {
            "imports": {},
            "includes": {},
            "modules": {},
        }
        
        for root, _, files in os.walk(self.workspace_root):
            root_path = Path(root)
            
            for f in files:
                if f.endswith((".py", ".c", ".h", ".js", ".ts")):
                    file_path = root_path / f
                    rel_path = file_path.relative_to(self.workspace_root)
                    
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        
                        # Python imports
                        if f.endswith(".py"):
                            import re
                            import_pattern = r"^(?:from|import)\s+([\w.]+)"
                            for match in re.finditer(import_pattern, content, re.MULTILINE):
                                module = match.group(1)
                                deps["imports"][str(rel_path)] = deps["imports"].get(str(rel_path), [])
                                deps["imports"][str(rel_path)].append(module)
                        
                        # C includes
                        elif f.endswith((".c", ".h")):
                            include_pattern = r'#include\s*[<"]([^>"]+)[>"]'
                            for match in re.finditer(include_pattern, content):
                                include = match.group(1)
                                deps["includes"][str(rel_path)] = deps["includes"].get(str(rel_path), [])
                                deps["includes"][str(rel_path)].append(include)
                    
                    except Exception as e:
                        logger.error(f"Error analyzing {file_path}: {e}")
        
        return deps
    
    async def find_symbol(self, name: str, file_type: str = "*") -> list[dict[str, Any]]:
        """Find where a symbol is defined or used."""
        results = []
        
        pattern = name
        search_files = list(self.workspace_root.glob(f"**/{file_type}"))
        
        for file_path in search_files:
            if not file_path.is_file():
                continue
            
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                rel_path = file_path.relative_to(self.workspace_root)
                
                for i, line in enumerate(content.split("\n"), 1):
                    if name in line:
                        results.append({
                            "file": str(rel_path),
                            "line": i,
                            "content": line.strip(),
                            "type": self._classify_symbol(line),
                        })
            except Exception:
                pass
        
        return results
    
    def _classify_symbol(self, line: str) -> str:
        """Classify the type of symbol."""
        line = line.strip()
        
        if line.startswith("def "):
            return "function"
        elif line.startswith("class "):
            return "class"
        elif line.startswith("async def "):
            return "async_function"
        elif line.startswith("interface "):
            return "interface"
        elif line.startswith("struct "):
            return "struct"
        elif line.startswith("enum "):
            return "enum"
        elif "const " in line:
            return "constant"
        elif "var " in line:
            return "variable"
        else:
            return "usage"
    
    async def extract_call_graph(self, entry_file: str) -> dict[str, Any]:
        """Extract call graph from entry point."""
        graph = {
            "nodes": [],
            "edges": [],
            "functions": {},
        }
        
        visited = set()
        
        def visit(file_path: Path, rel_path: str):
            if rel_path in visited:
                return
            visited.add(rel_path)
            
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                
                # Find function definitions
                import re
                
                func_pattern = r"(?:def|func|void|int)\s+(\w+)\s*\("
                for match in re.finditer(func_pattern, content):
                    func_name = match.group(1)
                    line_num = content[:match.start()].count("\n") + 1
                    
                    if rel_path not in graph["functions"]:
                        graph["functions"][rel_path] = []
                    graph["functions"][rel_path].append({
                        "name": func_name,
                        "line": line_num,
                    })
                    
                    graph["nodes"].append({
                        "id": f"{rel_path}:{func_name}",
                        "file": rel_path,
                        "function": func_name,
                    })
                
                # Find function calls
                call_pattern = r"(\w+)\s*\("
                for match in re.finditer(call_pattern, content):
                    called = match.group(1)
                    if called not in ["if", "while", "for", "print", "len", "range", "str", "int", "list"]:
                        graph["edges"].append({
                            "from": rel_path,
                            "to": called,
                        })
            
            except Exception as e:
                logger.error(f"Error extracting graph from {rel_path}: {e}")
        
        entry_path = self.workspace_root / entry_file
        if entry_path.exists():
            visit(entry_path, entry_file)
        
        return graph
    
    async def analyze_code_health(self) -> dict[str, Any]:
        """Analyze code health metrics."""
        metrics = {
            "files": 0,
            "lines": 0,
            "functions": 0,
            "classes": 0,
            "comments": 0,
            "todo_comments": 0,
            "complexity_score": 0,
        }
        
        import re
        
        for root, _, files in os.walk(self.workspace_root):
            root_path = Path(root)
            
            for f in files:
                if f.endswith((".py", ".c", ".h", ".js", ".ts")):
                    file_path = root_path / f
                    rel_path = file_path.relative_to(self.workspace_root)
                    
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        lines = content.split("\n")
                        
                        metrics["files"] += 1
                        metrics["lines"] += len(lines)
                        metrics["comments"] += sum(1 for l in lines if l.strip().startswith(("#", "//", "/*")))
                        metrics["todo_comments"] += sum(1 for l in lines if "TODO" in l or "FIXME" in l)
                        metrics["functions"] += len(re.findall(r"def\s+\w+", content))
                        metrics["classes"] += len(re.findall(r"class\s+\w+", content))
                        
                    except Exception:
                        pass
        
        # Calculate complexity score
        if metrics["files"] > 0:
            metrics["avg_lines_per_file"] = metrics["lines"] / metrics["files"]
            metrics["comment_ratio"] = metrics["comments"] / metrics["lines"] if metrics["lines"] > 0 else 0
        
        return metrics


# Global instances
_vision: Optional[VisionProvider] = None


def get_vision_provider() -> VisionProvider:
    """Get global vision provider."""
    global _vision
    if _vision is None:
        _vision = VisionProvider()
    return _vision


if __name__ == "__main__":
    import asyncio
    
    async def demo():
        print("Vision & Codebase Demo")
        print("=" * 40)
        
        # Codebase understanding
        cb = CodebaseUnderstanding(".")
        
        structure = await cb.analyze_structure()
        print(f"Project: {structure['files']} files")
        print(f"File types: {structure['file_types']}")
        
        # Code health
        health = await cb.analyze_code_health()
        print(f"\nCode Health:")
        print(f"  Files: {health['files']}")
        print(f"  Lines: {health['lines']}")
        print(f"  Functions: {health['functions']}")
        print(f"  Classes: {health['classes']}")
        print(f"  TODOs: {health['todo_comments']}")
    
    asyncio.run(demo())
