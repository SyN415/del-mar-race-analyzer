#!/usr/bin/env python3
"""
Docker Configuration Validator for Del Mar Race Analyzer
Validates Docker setup and Playwright configuration before deployment
"""

import os
import sys
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional

class DockerValidator:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.render_deploy_dir = self.project_root / "render-deploy"
        self.errors = []
        self.warnings = []
        self.success_count = 0
        self.total_checks = 0
    
    def print_header(self, text: str):
        print(f"\n{'='*50}")
        print(f"🐳 {text}")
        print(f"{'='*50}\n")
    
    def print_success(self, text: str):
        print(f"✅ {text}")
        self.success_count += 1
    
    def print_warning(self, text: str):
        print(f"⚠️  {text}")
        self.warnings.append(text)
    
    def print_error(self, text: str):
        print(f"❌ {text}")
        self.errors.append(text)
    
    def print_info(self, text: str):
        print(f"ℹ️  {text}")
    
    def check_file_exists(self, file_path: Path, description: str) -> bool:
        """Check if a required file exists"""
        self.total_checks += 1
        if file_path.exists():
            self.print_success(f"{description} exists: {file_path}")
            return True
        else:
            self.print_error(f"{description} missing: {file_path}")
            return False
    
    def check_dockerfile_content(self) -> bool:
        """Validate Dockerfile content"""
        self.total_checks += 1
        dockerfile_path = self.render_deploy_dir / "Dockerfile"
        
        if not dockerfile_path.exists():
            self.print_error("Dockerfile not found")
            return False
        
        content = dockerfile_path.read_text()
        
        # Check for required environment variables
        required_env_vars = [
            "PLAYWRIGHT_BROWSERS_PATH",
            "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"
        ]
        
        missing_env_vars = []
        for env_var in required_env_vars:
            if env_var not in content:
                missing_env_vars.append(env_var)
        
        if missing_env_vars:
            self.print_error(f"Missing environment variables in Dockerfile: {', '.join(missing_env_vars)}")
            return False
        
        # Check for Playwright installation
        if "playwright install chromium" not in content:
            self.print_error("Playwright browser installation not found in Dockerfile")
            return False
        
        # Check for system dependencies
        required_deps = ["libgbm1", "libnss3", "libatk-bridge2.0-0"]
        missing_deps = []
        for dep in required_deps:
            if dep not in content:
                missing_deps.append(dep)
        
        if missing_deps:
            self.print_warning(f"Some system dependencies might be missing: {', '.join(missing_deps)}")
        
        self.print_success("Dockerfile content validation passed")
        return True
    
    def check_render_yaml_content(self) -> bool:
        """Validate render.yaml content"""
        self.total_checks += 1
        render_yaml_path = self.render_deploy_dir / "render.yaml"
        
        if not render_yaml_path.exists():
            self.print_error("render.yaml not found")
            return False
        
        content = render_yaml_path.read_text()
        
        # Check for Docker runtime
        if "runtime: docker" not in content:
            self.print_error("render.yaml not configured for Docker runtime")
            return False
        
        # Check for Dockerfile path
        if "dockerfilePath:" not in content:
            self.print_error("dockerfilePath not specified in render.yaml")
            return False
        
        # Check for required environment variables
        required_env_vars = [
            "PLAYWRIGHT_BROWSERS_PATH",
            "ENVIRONMENT"
        ]
        
        missing_env_vars = []
        for env_var in required_env_vars:
            if env_var not in content:
                missing_env_vars.append(env_var)
        
        if missing_env_vars:
            self.print_warning(f"Environment variables might be missing in render.yaml: {', '.join(missing_env_vars)}")
        
        self.print_success("render.yaml content validation passed")
        return True
    
    def check_requirements_txt(self) -> bool:
        """Check if requirements.txt has necessary packages"""
        self.total_checks += 1
        requirements_path = self.project_root / "requirements.txt"
        
        if not requirements_path.exists():
            self.print_error("requirements.txt not found")
            return False
        
        content = requirements_path.read_text().lower()
        
        # Check for essential packages
        required_packages = ["playwright", "fastapi", "uvicorn"]
        missing_packages = []
        
        for package in required_packages:
            if package not in content:
                missing_packages.append(package)
        
        if missing_packages:
            self.print_error(f"Missing required packages in requirements.txt: {', '.join(missing_packages)}")
            return False
        
        self.print_success("requirements.txt validation passed")
        return True
    
    def check_app_structure(self) -> bool:
        """Check if the application structure is correct"""
        self.total_checks += 1
        app_py_path = self.project_root / "app.py"
        
        if not app_py_path.exists():
            self.print_error("app.py not found")
            return False
        
        # Check for FastAPI app
        content = app_py_path.read_text()
        if "FastAPI" not in content:
            self.print_warning("FastAPI not detected in app.py")
        
        # Check for health endpoint
        if "/health" not in content:
            self.print_warning("Health check endpoint not found in app.py")
        
        self.print_success("Application structure validation passed")
        return True
    
    def check_docker_availability(self) -> bool:
        """Check if Docker is available for local testing"""
        self.total_checks += 1
        try:
            result = subprocess.run(["docker", "--version"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.print_success(f"Docker available: {result.stdout.strip()}")
                return True
            else:
                self.print_warning("Docker not available for local testing")
                return False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self.print_warning("Docker not available for local testing")
            return False
    
    def validate_environment_variables(self) -> bool:
        """Validate environment variable configuration"""
        self.total_checks += 1
        
        # Check if .env file exists (optional)
        env_file = self.project_root / ".env"
        if env_file.exists():
            self.print_info("Found .env file for local development")
        
        # List required environment variables for production
        required_env_vars = [
            "OPENROUTER_API_KEY",
            "ENVIRONMENT",
            "PLAYWRIGHT_BROWSERS_PATH"
        ]
        
        self.print_info("Required environment variables for production:")
        for var in required_env_vars:
            print(f"   - {var}")
        
        self.print_success("Environment variable configuration reviewed")
        return True
    
    def run_validation(self) -> bool:
        """Run all validation checks"""
        self.print_header("Docker Configuration Validator")
        
        # File existence checks
        self.check_file_exists(self.render_deploy_dir / "Dockerfile", "Docker configuration")
        self.check_file_exists(self.render_deploy_dir / "render.yaml", "Render.com configuration")
        self.check_file_exists(self.project_root / "requirements.txt", "Python requirements")
        self.check_file_exists(self.project_root / "app.py", "Main application")
        
        # Content validation checks
        self.check_dockerfile_content()
        self.check_render_yaml_content()
        self.check_requirements_txt()
        self.check_app_structure()
        
        # Environment checks
        self.check_docker_availability()
        self.validate_environment_variables()
        
        # Print summary
        self.print_summary()
        
        return len(self.errors) == 0
    
    def print_summary(self):
        """Print validation summary"""
        self.print_header("Validation Summary")
        
        print(f"✅ Successful checks: {self.success_count}/{self.total_checks}")
        
        if self.warnings:
            print(f"\n⚠️  Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"   - {warning}")
        
        if self.errors:
            print(f"\n❌ Errors ({len(self.errors)}):")
            for error in self.errors:
                print(f"   - {error}")
            print("\n🔧 Please fix the errors before deploying.")
        else:
            print("\n🎉 All validation checks passed! Your Docker configuration is ready for deployment.")
            print("\n📋 Next steps:")
            print("   1. Run ./deploy-docker.sh for deployment instructions")
            print("   2. Set up your service on Render.com")
            print("   3. Configure environment variables")
            print("   4. Deploy and monitor the build logs")

def main():
    """Main function"""
    validator = DockerValidator()
    success = validator.run_validation()
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
