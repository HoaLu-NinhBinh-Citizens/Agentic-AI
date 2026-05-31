"""FastAPI missing validation rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class MissingValidationRule:
    """Detect FastAPI endpoints without Pydantic validation.

    FastAPI's power comes from automatic validation via Pydantic models.
    Without them, data is not validated before reaching your endpoint.
    """

    rule_id: str = "FASTAPI004"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        endpoint_pattern = r'@(?:app|router)\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']'
        path_param_pattern = r'\{(\w+)\}'
        
        has_fastapi = 'fastapi' in content.lower() or 'FastAPI' in content
        
        if not has_fastapi:
            return findings

        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            endpoint_match = re.search(endpoint_pattern, line)
            if endpoint_match:
                method, path = endpoint_match.groups()
                path_params = re.findall(path_param_pattern, path)
                
                next_lines = '\n'.join(lines[i:min(i+15, len(lines))])
                func_def_match = re.search(r'async\s+def\s+\w+\s*\(([^)]*)\)', next_lines)
                
                if func_def_match:
                    params = func_def_match.group(1)
                    has_typed_params = any(
                        p in params and ':' in params[params.index(p):]
                        for p in path_params
                    )
                    has_pydantic = 'BaseModel' in content or 'pydantic' in content.lower()
                    has_body = 'Body' in next_lines or 'Form' in next_lines
                    
                    if path_params and not has_typed_params:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Path parameter in {path} may lack type validation",
                            "explanation": "FastAPI path parameters should have type hints for automatic "
                                           "OpenAPI documentation and validation.",
                            "fix": f"Add type hint: @app.{method}('{path}') with def endpoint({path_params[0]}: int)",
                        })
                    
                    if method == 'post' and has_pydantic and not has_body:
                        if 'Request' in params or params.strip() == '':
                            findings.append({
                                "rule_id": self.rule_id,
                                "severity": self.severity.value,
                                "file": file_path,
                                "line": i,
                                "message": f"POST endpoint {path} may lack request body validation",
                                "explanation": "POST endpoints typically need a Pydantic model for body validation.",
                                "fix": "Create a Pydantic model: class Item(BaseModel): name: str",
                            })

        return findings
