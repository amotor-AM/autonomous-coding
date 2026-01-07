#!/usr/bin/env python3
"""
Autonomous Coding Agent Demo
============================

A minimal harness demonstrating long-running autonomous coding with Claude.
This script implements the two-agent pattern (initializer + coding agent) and
incorporates all the strategies from the long-running agents guide.

Supports hybrid model usage: Opus for planning/initialization, Sonnet for implementation.

Example Usage:
    python autonomous_agent_demo.py
    python autonomous_agent_demo.py --hybrid  # Uses Opus + Sonnet
"""

import argparse
import asyncio
import os
from pathlib import Path

from agent import run_autonomous_agent
from prompts import list_specs, get_available_specs


# Configuration - Claude 4.5 models
MODEL_OPUS = "claude-opus-4-5-20251101"
MODEL_SONNET = "claude-sonnet-4-5-20250930"
DEFAULT_MODEL = MODEL_SONNET


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Autonomous Coding Agent Demo - Long-running agent harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start project with Sonnet (default) - outputs to generations/app
  python autonomous_agent_demo.py

  # Use HYBRID mode: Opus for planning, Sonnet for implementation
  python autonomous_agent_demo.py --hybrid

  # Use Opus only (more capable but uses quota faster)
  python autonomous_agent_demo.py --model claude-opus-4-5-20251101

  # List available spec files
  python autonomous_agent_demo.py --list-specs

  # Limit iterations for testing
  python autonomous_agent_demo.py --max-iterations 5

  # Custom output directory
  python autonomous_agent_demo.py --project-dir ./my_custom_project

Authentication:
  With Claude Pro subscription, authenticate via:
    npm install -g @anthropic-ai/claude-code
    claude  # Opens browser for OAuth login
        """,
    )

    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path("./generations/app"),
        help="Directory for the project. Default: generations/app",
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum number of agent iterations (default: unlimited)",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL})",
    )

    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Use hybrid mode: Opus 4.5 for planning/initialization, Sonnet 4.5 for implementation. Best of both worlds!",
    )

    parser.add_argument(
        "--spec-file",
        type=str,
        default=None,
        help="Custom spec file to use (e.g., nvmercantile_spec.txt). See --list-specs for available options.",
    )

    parser.add_argument(
        "--list-specs",
        action="store_true",
        help="List available spec files and exit",
    )

    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Handle --list-specs
    if args.list_specs:
        list_specs()
        return

    # Validate spec file if provided
    if args.spec_file:
        available = get_available_specs()
        if args.spec_file not in available:
            print(f"Error: Spec file '{args.spec_file}' not found.")
            list_specs()
            return

    # Check for authentication (either API key or Claude Code OAuth)
    has_api_key = os.environ.get("ANTHROPIC_API_KEY")
    claude_dir = Path.home() / ".claude"
    has_oauth = claude_dir.exists() and any(claude_dir.iterdir()) if claude_dir.exists() else False
    
    if not has_api_key and not has_oauth:
        print("Error: No authentication found")
        print("\nOption 1 - Claude Pro subscription (recommended):")
        print("  npm install -g @anthropic-ai/claude-code")
        print("  claude  # Opens browser for OAuth login")
        print("\nOption 2 - API key:")
        print("  export ANTHROPIC_API_KEY='your-api-key-here'")
        return

    # Use project directory as specified
    project_dir = args.project_dir

    # Determine models based on --hybrid flag
    if args.hybrid:
        planning_model = MODEL_OPUS
        coding_model = MODEL_SONNET
        print("\n🎯 HYBRID MODE: Opus 4.5 (planning) + Sonnet 4.5 (implementation)")
    else:
        planning_model = args.model
        coding_model = args.model

    # Run the agent
    try:
        asyncio.run(
            run_autonomous_agent(
                project_dir=project_dir,
                planning_model=planning_model,
                coding_model=coding_model,
                max_iterations=args.max_iterations,
                spec_file=args.spec_file,
            )
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        print("To resume, run the same command again")
    except Exception as e:
        print(f"\nFatal error: {e}")
        raise


if __name__ == "__main__":
    main()
