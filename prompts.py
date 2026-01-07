"""
Prompt Loading Utilities
========================

Functions for loading prompt templates from the prompts directory.
Supports custom spec files for different projects (e.g., NVMercantile/Nexus).
"""

import shutil
from pathlib import Path


PROMPTS_DIR = Path(__file__).parent / "prompts"

# Default spec file - can be overridden via CLI
DEFAULT_SPEC_FILE = "app_spec.txt"


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{name}.md"
    return prompt_path.read_text()


def get_initializer_prompt() -> str:
    """Load the initializer prompt."""
    return load_prompt("initializer_prompt")


def get_coding_prompt() -> str:
    """Load the coding agent prompt."""
    return load_prompt("coding_prompt")


def get_available_specs() -> list[str]:
    """List all available spec files in the prompts directory."""
    specs = []
    for f in PROMPTS_DIR.glob("*.txt"):
        specs.append(f.name)
    return sorted(specs)


def copy_spec_to_project(project_dir: Path, spec_file: str | None = None) -> None:
    """
    Copy the app spec file into the project directory for the agent to read.
    
    Args:
        project_dir: Target project directory
        spec_file: Optional custom spec file name (e.g., "nvmercantile_spec.txt")
                   If None, uses the default "app_spec.txt"
    """
    # Determine source spec file
    if spec_file:
        spec_source = PROMPTS_DIR / spec_file
        if not spec_source.exists():
            raise FileNotFoundError(f"Spec file not found: {spec_source}")
    else:
        spec_source = PROMPTS_DIR / DEFAULT_SPEC_FILE
    
    # Always copy to "app_spec.txt" in project so prompts can reference it consistently
    spec_dest = project_dir / "app_spec.txt"
    
    # Copy if not exists, or if using a different spec file
    if not spec_dest.exists() or spec_file:
        shutil.copy(spec_source, spec_dest)
        if spec_file and spec_file != DEFAULT_SPEC_FILE:
            print(f"Copied {spec_file} -> project/app_spec.txt")
        else:
            print("Copied app_spec.txt to project directory")


def list_specs() -> None:
    """Print available spec files."""
    print("\nAvailable spec files:")
    for spec in get_available_specs():
        marker = " (default)" if spec == DEFAULT_SPEC_FILE else ""
        print(f"  - {spec}{marker}")
    print()
