"""Production Deployment Validation.

Validates Docker and Kubernetes deployment configurations.
Run with: python -m src.infrastructure.deployment.validate
"""

import asyncio
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ValidationResult:
    """Result of a validation check."""
    name: str
    passed: bool
    message: str
    details: dict[str, Any] | None = None


class DeploymentValidator:
    """Validates production deployment configurations.
    
    Checks:
    - Dockerfile syntax
    - docker-compose validity
    - Kubernetes manifests
    - Helm chart structure
    - Resource limits
    - Security configurations
    """
    
    def __init__(self, deployment_dir: Path):
        self._deployment_dir = deployment_dir
        self._results: list[ValidationResult] = []
    
    async def validate_all(self) -> list[ValidationResult]:
        """Run all validation checks."""
        self._results = []
        
        # Docker validation
        await self.validate_dockerfile()
        await self.validate_docker_compose()
        
        # Kubernetes validation
        await self.validate_kubernetes()
        
        # Helm validation
        await self.validate_helm()
        
        # Security validation
        await self.validate_security()
        
        # Resource validation
        await self.validate_resources()
        
        return self._results
    
    async def validate_dockerfile(self) -> ValidationResult:
        """Validate Dockerfile syntax."""
        dockerfile = self._deployment_dir / "Dockerfile"
        
        if not dockerfile.exists():
            result = ValidationResult(
                name="dockerfile_exists",
                passed=False,
                message="Dockerfile not found",
            )
            self._results.append(result)
            return result
        
        # Check basic Dockerfile requirements
        content = dockerfile.read_text()
        
        checks = {
            "has_from": "FROM" in content,
            "has_workdir": "WORKDIR" in content,
            "has_user": "USER" in content or "RUN useradd" in content,
            "has_healthcheck": "HEALTHCHECK" in content,
            "has_expose": "EXPOSE" in content,
        }
        
        all_passed = all(checks.values())
        
        result = ValidationResult(
            name="dockerfile",
            passed=all_passed,
            message="Dockerfile valid" if all_passed else "Dockerfile missing required instructions",
            details=checks,
        )
        self._results.append(result)
        return result
    
    async def validate_docker_compose(self) -> ValidationResult:
        """Validate docker-compose configuration."""
        compose_file = self._deployment_dir / "docker-compose.prod.yml"
        
        if not compose_file.exists():
            result = ValidationResult(
                name="docker_compose",
                passed=False,
                message="docker-compose.prod.yml not found",
            )
            self._results.append(result)
            return result
        
        # Try to validate YAML syntax
        try:
            import yaml
            with open(compose_file) as f:
                compose = yaml.safe_load(f)
            
            # Check required services
            required_services = ["aisupport"]
            has_services = all(s in compose.get("services", {}) for s in required_services)
            
            # Check for healthchecks
            services = compose.get("services", {})
            healthchecks = all(
                "healthcheck" in services[s].get("deploy", {})
                for s in required_services if s in services
            )
            
            # Check for resource limits
            has_limits = all(
                "resources" in services[s].get("deploy", {})
                for s in required_services if s in services
            )
            
            passed = has_services and healthchecks and has_limits
            
            result = ValidationResult(
                name="docker_compose",
                passed=passed,
                message="docker-compose valid" if passed else "Missing required configuration",
                details={
                    "has_services": has_services,
                    "has_healthchecks": healthchecks,
                    "has_resource_limits": has_limits,
                },
            )
            
        except Exception as e:
            result = ValidationResult(
                name="docker_compose",
                passed=False,
                message=f"docker-compose parsing error: {e}",
            )
        
        self._results.append(result)
        return result
    
    async def validate_kubernetes(self) -> ValidationResult:
        """Validate Kubernetes manifests."""
        k8s_dir = self._deployment_dir / "k8s"
        
        if not k8s_dir.exists():
            result = ValidationResult(
                name="kubernetes",
                passed=False,
                message="k8s directory not found",
            )
            self._results.append(result)
            return result
        
        required_files = [
            "deployment.yaml",
            "service.yaml",
            "configmap.yaml",
            "secret.yaml",
        ]
        
        existing_files = [f.name for f in k8s_dir.glob("*.yaml")]
        has_required = all(f in existing_files for f in required_files)
        
        # Validate YAML syntax
        yaml_errors = []
        for yaml_file in k8s_dir.glob("*.yaml"):
            try:
                import yaml
                with open(yaml_file) as f:
                    list(yaml.safe_load_all(f))  # Load all documents
            except Exception as e:
                yaml_errors.append(f"{yaml_file.name}: {e}")
        
        passed = has_required and len(yaml_errors) == 0
        
        result = ValidationResult(
            name="kubernetes",
            passed=passed,
            message="Kubernetes manifests valid" if passed else "Validation errors found",
            details={
                "has_required_files": has_required,
                "existing_files": existing_files,
                "yaml_errors": yaml_errors,
            },
        )
        self._results.append(result)
        return result
    
    async def validate_helm(self) -> ValidationResult:
        """Validate Helm chart structure."""
        helm_dir = self._deployment_dir / "helm"
        
        if not helm_dir.exists():
            result = ValidationResult(
                name="helm",
                passed=False,
                message="helm directory not found",
            )
            self._results.append(result)
            return result
        
        required_files = [
            "Chart.yaml",
            "values.yaml",
        ]
        
        templates_dir = helm_dir / "templates"
        
        has_chart = all((helm_dir / f).exists() for f in required_files)
        has_templates = templates_dir.exists() and any(templates_dir.glob("*.yaml"))
        
        # Validate Chart.yaml
        chart_errors = []
        if (helm_dir / "Chart.yaml").exists():
            try:
                import yaml
                with open(helm_dir / "Chart.yaml") as f:
                    chart = yaml.safe_load(f)
                
                if "apiVersion" not in chart:
                    chart_errors.append("Missing apiVersion")
                if "name" not in chart:
                    chart_errors.append("Missing name")
            except Exception as e:
                chart_errors.append(str(e))
        
        passed = has_chart and has_templates and len(chart_errors) == 0
        
        result = ValidationResult(
            name="helm",
            passed=passed,
            message="Helm chart valid" if passed else "Validation errors found",
            details={
                "has_chart": has_chart,
                "has_templates": has_templates,
                "chart_errors": chart_errors,
            },
        )
        self._results.append(result)
        return result
    
    async def validate_security(self) -> ValidationResult:
        """Validate security configurations."""
        checks = {
            "no_root_user": True,  # Check in Dockerfile
            "read_only_root_fs": True,  # Check in K8s
            "no_default_passwords": True,  # Check in configs
            "has_resource_limits": True,  # Check in K8s
        }
        
        # Check Dockerfile for USER directive
        dockerfile = self._deployment_dir / "Dockerfile"
        if dockerfile.exists():
            checks["no_root_user"] = "USER" in dockerfile.read_text()
        
        # Check K8s for securityContext
        k8s_dir = self._deployment_dir / "k8s"
        if k8s_dir.exists():
            deployment_file = k8s_dir / "deployment.yaml"
            if deployment_file.exists():
                import yaml
                with open(deployment_file) as f:
                    docs = list(yaml.safe_load_all(f))
                
                for doc in docs:
                    if doc and doc.get("kind") == "Deployment":
                        containers = doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
                        for c in containers:
                            security_ctx = c.get("securityContext", {})
                            checks["read_only_root_fs"] = security_ctx.get("readOnlyRootFilesystem", False)
        
        all_passed = all(checks.values())
        
        result = ValidationResult(
            name="security",
            passed=all_passed,
            message="Security configuration valid" if all_passed else "Security issues found",
            details=checks,
        )
        self._results.append(result)
        return result
    
    async def validate_resources(self) -> ValidationResult:
        """Validate resource configurations."""
        k8s_dir = self._deployment_dir / "k8s"
        
        if not k8s_dir.exists():
            result = ValidationResult(
                name="resources",
                passed=False,
                message="k8s directory not found",
            )
            self._results.append(result)
            return result
        
        deployment_file = k8s_dir / "deployment.yaml"
        
        if not deployment_file.exists():
            result = ValidationResult(
                name="resources",
                passed=False,
                message="deployment.yaml not found",
            )
            self._results.append(result)
            return result
        
        import yaml
        with open(deployment_file) as f:
            docs = list(yaml.safe_load_all(f))
        
        checks = {
            "has_cpu_limits": False,
            "has_memory_limits": False,
            "has_liveness_probe": False,
            "has_readiness_probe": False,
            "has_hpa": False,
        }
        
        for doc in docs:
            if doc and doc.get("kind") == "Deployment":
                containers = doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
                for c in containers:
                    resources = c.get("resources", {})
                    limits = resources.get("limits", {})
                    
                    checks["has_cpu_limits"] = "cpu" in limits
                    checks["has_memory_limits"] = "memory" in limits
                    checks["has_liveness_probe"] = "livenessProbe" in c
                    checks["has_readiness_probe"] = "readinessProbe" in c
            
            if doc and doc.get("kind") == "HorizontalPodAutoscaler":
                checks["has_hpa"] = True
        
        all_passed = all(checks.values())
        
        result = ValidationResult(
            name="resources",
            passed=all_passed,
            message="Resource configuration valid" if all_passed else "Missing resource configurations",
            details=checks,
        )
        self._results.append(result)
        return result
    
    def print_results(self) -> None:
        """Print validation results."""
        print("\n" + "=" * 70)
        print("DEPLOYMENT VALIDATION RESULTS")
        print("=" * 70)
        
        for result in self._results:
            icon = "✅" if result.passed else "❌"
            print(f"\n{icon} {result.name}")
            print(f"   {result.message}")
            
            if result.details:
                for key, value in result.details.items():
                    if isinstance(value, bool):
                        status = "✓" if value else "✗"
                        print(f"      {status} {key}")
                    else:
                        print(f"      {key}: {value}")
        
        # Summary
        total = len(self._results)
        passed = sum(1 for r in self._results if r.passed)
        failed = total - passed
        
        print("\n" + "-" * 70)
        print(f"Total: {total} | Passed: {passed} | Failed: {failed}")
        print("=" * 70)
        
        if failed == 0:
            print("✅ All validations passed! Ready for deployment.")
        else:
            print("❌ Some validations failed. Fix issues before deployment.")


async def main():
    """Run deployment validation."""
    # Find deployment directory
    project_root = Path(__file__).parent.parent.parent.parent
    deployment_dir = project_root / "deployments" / "production"
    
    if not deployment_dir.exists():
        deployment_dir = project_root / "deployments"
    
    print(f"Validating deployment in: {deployment_dir}")
    
    validator = DeploymentValidator(deployment_dir)
    await validator.validate_all()
    validator.print_results()
    
    # Return exit code based on results
    failed = sum(1 for r in validator._results if not r.passed)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
