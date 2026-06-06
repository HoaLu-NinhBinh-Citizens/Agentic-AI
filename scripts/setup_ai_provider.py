#!/usr/bin/env python3
"""
AI Provider Setup Script for AI_SUPPORT

This script helps users configure AI providers for AI_SUPPORT.
It guides through setup of OpenAI, Ollama, or Anthropic providers.
"""

import os
import sys
import subprocess
import platform
import json
from pathlib import Path

def print_header():
    """Print setup header."""
    print("=" * 60)
    print("AI_SUPPORT - AI Provider Setup")
    print("=" * 60)
    print()

def check_ollama_installation():
    """Check if Ollama is installed and running."""
    print("Checking Ollama installation...")
    
    # Check if ollama command exists
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("✅ Ollama is installed")
            ollama_version = result.stdout.strip()
            print(f"   Version: {ollama_version}")
            return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("❌ Ollama is not installed")
        return False
    
    return False

def check_ollama_running():
    """Check if Ollama server is running."""
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            print("✅ Ollama server is running")
            return True
    except Exception:
        print("❌ Ollama server is not running")
        return False
    
    return False

def check_environment_variables():
    """Check for AI provider environment variables."""
    print("\nChecking environment variables...")
    
    vars_found = []
    
    if os.getenv("OPENAI_API_KEY"):
        print("✅ OPENAI_API_KEY is set")
        vars_found.append("openai")
    else:
        print("❌ OPENAI_API_KEY is not set")
    
    if os.getenv("ANTHROPIC_API_KEY"):
        print("✅ ANTHROPIC_API_KEY is set")
        vars_found.append("anthropic")
    else:
        print("❌ ANTHROPIC_API_KEY is not set")
    
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    print(f"📊 OLLAMA_BASE_URL: {ollama_url}")
    
    return vars_found

def install_ollama():
    """Install Ollama based on operating system."""
    system = platform.system().lower()
    
    print("\nInstalling Ollama...")
    
    if system == "windows":
        print("Please download and install Ollama from:")
        print("  https://ollama.ai/download/windows")
        print("\nAfter installation, run:")
        print("  ollama serve")
        return False
    
    elif system == "darwin":  # macOS
        print("Installing via Homebrew...")
        try:
            subprocess.run(["brew", "install", "ollama"], check=True)
            print("✅ Ollama installed via Homebrew")
            return True
        except Exception as e:
            print(f"❌ Failed to install via Homebrew: {e}")
            print("\nAlternative: Download from https://ollama.ai/download/mac")
            return False
    
    elif system == "linux":
        print("Installing via curl script...")
        try:
            install_cmd = "curl -fsSL https://ollama.ai/install.sh | sh"
            print(f"Running: {install_cmd}")
            # Note: This requires user interaction
            subprocess.run(install_cmd, shell=True, check=True)
            print("✅ Ollama installed")
            return True
        except Exception as e:
            print(f"❌ Failed to install: {e}")
            return False
    
    else:
        print(f"❌ Unsupported operating system: {system}")
        return False

def configure_openai():
    """Configure OpenAI API key."""
    print("\n--- OpenAI Configuration ---")
    api_key = input("Enter your OpenAI API key (or press Enter to skip): ").strip()
    
    if api_key:
        # Add to environment
        os.environ["OPENAI_API_KEY"] = api_key
        
        # Suggest adding to shell profile
        shell_profile = get_shell_profile()
        if shell_profile:
            with open(shell_profile, "a") as f:
                f.write(f'\nexport OPENAI_API_KEY="{api_key}"\n')
            print(f"✅ Added OPENAI_API_KEY to {shell_profile}")
        else:
            print("✅ OPENAI_API_KEY set for current session")
            print("   To make permanent, add to your shell profile:")
            print(f'   export OPENAI_API_KEY="{api_key}"')
        
        return True
    else:
        print("⚠️  OpenAI configuration skipped")
        return False

def configure_anthropic():
    """Configure Anthropic API key."""
    print("\n--- Anthropic Configuration ---")
    api_key = input("Enter your Anthropic API key (or press Enter to skip): ").strip()
    
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
        
        shell_profile = get_shell_profile()
        if shell_profile:
            with open(shell_profile, "a") as f:
                f.write(f'\nexport ANTHROPIC_API_KEY="{api_key}"\n')
            print(f"✅ Added ANTHROPIC_API_KEY to {shell_profile}")
        else:
            print("✅ ANTHROPIC_API_KEY set for current session")
            print("   To make permanent, add to your shell profile:")
            print(f'   export ANTHROPIC_API_KEY="{api_key}"')
        
        return True
    else:
        print("⚠️  Anthropic configuration skipped")
        return False

def get_shell_profile():
    """Get the user's shell profile path."""
    shell = os.getenv("SHELL", "")
    
    if "zsh" in shell:
        return os.path.expanduser("~/.zshrc")
    elif "bash" in shell:
        return os.path.expanduser("~/.bashrc")
    elif "fish" in shell:
        return os.path.expanduser("~/.config/fish/config.fish")
    else:
        # Default to bashrc
        bashrc = os.path.expanduser("~/.bashrc")
        if os.path.exists(bashrc):
            return bashrc
        return None

def test_ai_connection():
    """Test AI connection by starting server and making request."""
    print("\n--- Testing AI Connection ---")
    
    # First, check if server is already running
    try:
        import requests
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            print("✅ AI_SUPPORT server is running")
            server_running = True
        else:
            server_running = False
    except Exception:
        server_running = False
    
    if not server_running:
        print("⚠️  AI_SUPPORT server is not running")
        print("   Start it with: python src/interfaces/server/main.py")
        print("   Then run this test again.")
        return False
    
    # Test configuration status
    try:
        response = requests.get("http://localhost:8000/api/ai/config/status", timeout=10)
        if response.status_code == 200:
            status = response.json()
            print(f"✅ Configuration status retrieved")
            print(f"   Configured: {status.get('configured', False)}")
            
            if status.get('configured'):
                providers = status.get('providers', {})
                for provider, info in providers.items():
                    if info.get('available'):
                        print(f"   ✅ {provider.upper()}: Available")
                    else:
                        print(f"   ❌ {provider.upper()}: Not available")
                
                # Test actual AI response
                print("\nTesting AI response...")
                test_response = requests.post(
                    "http://localhost:8000/api/ai/test",
                    json={"prompt": "Test connection"},
                    timeout=30
                )
                
                if test_response.status_code == 200:
                    test_result = test_response.json()
                    if test_result.get('success'):
                        print("✅ AI test successful!")
                        print(f"   Provider: {test_result.get('provider')}")
                        print(f"   Response: {test_result.get('response', '')[:100]}...")
                    else:
                        print("❌ AI test failed")
                        print(f"   Error: {test_result.get('error')}")
                        print(f"   Message: {test_result.get('message')}")
                else:
                    print(f"❌ Test request failed: {test_response.status_code}")
            else:
                print("❌ No AI providers configured")
                suggestions = status.get('suggestions', [])
                for suggestion in suggestions:
                    print(f"   💡 {suggestion}")
            
            return status.get('configured', False)
        else:
            print(f"❌ Failed to get status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing connection: {e}")
        return False

def print_summary():
    """Print configuration summary."""
    print("\n" + "=" * 60)
    print("SETUP SUMMARY")
    print("=" * 60)
    
    # Check what's configured
    openai_key = bool(os.getenv("OPENAI_API_KEY"))
    anthropic_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    ollama_installed = check_ollama_installation()
    ollama_running = check_ollama_running() if ollama_installed else False
    
    print("\nConfiguration Status:")
    print(f"  OpenAI: {'✅ Configured' if openai_key else '❌ Not configured'}")
    print(f"  Anthropic: {'✅ Configured' if anthropic_key else '❌ Not configured'}")
    print(f"  Ollama: {'✅ Installed & Running' if ollama_running else '❌ Not available'}")
    
    print("\nNext Steps:")
    print("1. Start AI_SUPPORT server:")
    print("   python src/interfaces/server/main.py")
    print("\n2. Test your setup:")
    print("   python scripts/setup_ai_provider.py --test")
    print("\n3. For embedded engineering, pull specialized models:")
    print("   ollama pull codellama")
    print("   ollama pull deepseek-coder")
    
    print("\n4. View detailed documentation:")
    print("   docs/AI_CONFIGURATION_GUIDE.md")

def main():
    """Main setup function."""
    print_header()
    
    print("This script will help you configure AI providers for AI_SUPPORT.")
    print("You can configure one or more of:")
    print("  • OpenAI GPT (cloud, requires API key)")
    print("  • Ollama (local, free, recommended for embedded)")
    print("  • Anthropic Claude (cloud, requires API key)")
    print()
    
    # Check current status
    current_vars = check_environment_variables()
    ollama_installed = check_ollama_installation()
    ollama_running = check_ollama_running() if ollama_installed else False
    
    if not current_vars and not ollama_running:
        print("\n⚠️  No AI providers configured. Let's set one up.")
    
    # Ask which provider to configure
    print("\nSelect provider to configure:")
    print("1. OpenAI (cloud, best quality)")
    print("2. Ollama (local, free, good for embedded)")
    print("3. Anthropic (cloud)")
    print("4. Test current configuration")
    print("5. Exit")
    
    choice = input("\nEnter choice (1-5): ").strip()
    
    if choice == "1":
        configure_openai()
    elif choice == "2":
        if not ollama_installed:
            print("\nOllama is not installed.")
            install = input("Install Ollama now? (y/n): ").lower()
            if install == "y":
                if install_ollama():
                    print("\n✅ Ollama installed. Please run:")
                    print("   ollama serve")
                    print("\nThen restart this setup script.")
                else:
                    print("\n❌ Ollama installation failed.")
        elif not ollama_running:
            print("\n⚠️  Ollama is installed but not running.")
            print("Start it with: ollama serve")
            print("Then restart this setup script.")
        else:
            print("\n✅ Ollama is already installed and running.")
            print("You can pull models: ollama pull llama3.2")
    elif choice == "3":
        configure_anthropic()
    elif choice == "4":
        test_ai_connection()
    elif choice == "5":
        print("\nExiting setup.")
        sys.exit(0)
    else:
        print("\n❌ Invalid choice.")
    
    # Print summary
    print_summary()
    
    # Save configuration
    config_path = Path.home() / ".ai_support_config.json"
    config = {
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "anthropic_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
        "ollama_available": ollama_running,
        "setup_completed": True,
        "timestamp": str(Path(__file__).stat().st_mtime)
    }
    
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    
    print(f"\n✅ Configuration saved to {config_path}")

if __name__ == "__main__":
    try:
        import requests
    except ImportError:
        print("Installing required packages...")
        subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True)
        import requests
    
    main()