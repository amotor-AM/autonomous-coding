"""
Agent Session Logic
===================

Core agent interaction functions for running autonomous coding sessions.
Includes rate limit handling for Claude Pro subscription usage.
"""

import asyncio
import time
from pathlib import Path
from typing import Optional

from claude_agent_sdk import ClaudeSDKClient

from client import create_client
from progress import print_session_header, print_progress_summary
from prompts import get_initializer_prompt, get_coding_prompt, copy_spec_to_project


# Configuration
AUTO_CONTINUE_DELAY_SECONDS = 3

# Rate limit handling configuration
# Fallback wait times when retry-after header is not available:
#   - First fallback: 5 hours
#   - If throttled again immediately after fallback wait: 24 hours
FALLBACK_WAIT_FIRST_SECONDS = 5 * 60 * 60   # 5 hours
FALLBACK_WAIT_EXTENDED_SECONDS = 24 * 60 * 60  # 24 hours
MAX_RATE_LIMIT_WAIT_SECONDS = 24 * 60 * 60  # 24 hours max wait
RATE_LIMIT_RETRY_COUNT = 10  # Max retries before giving up


def parse_rate_limit_error(error_str: str) -> Optional[int]:
    """
    Parse rate limit error to extract wait time.
    
    Looks for:
    - retry-after header value
    - Common patterns in error messages
    
    Returns wait time in seconds, or None if not a rate limit error.
    """
    error_lower = error_str.lower()
    
    # Check if this is a rate limit error
    rate_limit_indicators = [
        "rate limit",
        "rate_limit",
        "429",
        "too many requests",
        "quota exceeded",
        "overloaded",
    ]
    
    is_rate_limit = any(indicator in error_lower for indicator in rate_limit_indicators)
    if not is_rate_limit:
        return None
    
    # Try to extract retry-after value
    import re
    
    # Look for "retry-after: X" or "retry_after: X" or "wait X seconds"
    patterns = [
        r'retry[-_]after[:\s]+(\d+)',
        r'wait\s+(\d+)\s*(?:seconds?|s)',
        r'try again in\s+(\d+)',
        r'(\d+)\s*seconds?\s+(?:before|until)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, error_lower)
        if match:
            return int(match.group(1))
    
    # No specific time found, return None to signal fallback should be used
    return None


def get_fallback_wait_time(used_fallback_last_time: bool) -> int:
    """
    Get the fallback wait time when retry-after header is not available.
    
    Args:
        used_fallback_last_time: True if the previous wait also used fallback
                                 (no header was found then either)
    
    Returns:
        Wait time in seconds:
        - 5 hours on first fallback
        - 24 hours if throttled again immediately after a fallback wait
    """
    if used_fallback_last_time:
        return FALLBACK_WAIT_EXTENDED_SECONDS
    return FALLBACK_WAIT_FIRST_SECONDS


def format_wait_time(seconds: int) -> str:
    """Format seconds into human-readable string."""
    if seconds < 60:
        return f"{seconds} seconds"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if minutes > 0:
            return f"{hours} hour{'s' if hours != 1 else ''} {minutes} min"
        return f"{hours} hour{'s' if hours != 1 else ''}"


async def run_agent_session(
    client: ClaudeSDKClient,
    message: str,
    project_dir: Path,
) -> tuple[str, str]:
    """
    Run a single agent session using Claude Agent SDK.

    Args:
        client: Claude SDK client
        message: The prompt to send
        project_dir: Project directory path

    Returns:
        (status, response_text) where status is:
        - "continue" if agent should continue working
        - "rate_limited" if hit rate limit (caller should wait and retry)
        - "error" if an error occurred
    """
    print("Sending prompt to Claude Agent SDK...\n")

    try:
        # Send the query
        await client.query(message)

        # Collect response text and show tool use
        response_text = ""
        async for msg in client.receive_response():
            msg_type = type(msg).__name__

            # Handle AssistantMessage (text and tool use)
            if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    block_type = type(block).__name__

                    if block_type == "TextBlock" and hasattr(block, "text"):
                        response_text += block.text
                        print(block.text, end="", flush=True)
                    elif block_type == "ToolUseBlock" and hasattr(block, "name"):
                        print(f"\n[Tool: {block.name}]", flush=True)
                        if hasattr(block, "input"):
                            input_str = str(block.input)
                            if len(input_str) > 200:
                                print(f"   Input: {input_str[:200]}...", flush=True)
                            else:
                                print(f"   Input: {input_str}", flush=True)

            # Handle UserMessage (tool results)
            elif msg_type == "UserMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    block_type = type(block).__name__

                    if block_type == "ToolResultBlock":
                        result_content = getattr(block, "content", "")
                        is_error = getattr(block, "is_error", False)

                        # Check if command was blocked by security hook
                        if "blocked" in str(result_content).lower():
                            print(f"   [BLOCKED] {result_content}", flush=True)
                        elif is_error:
                            # Show errors (truncated)
                            error_str = str(result_content)[:500]
                            print(f"   [Error] {error_str}", flush=True)
                        else:
                            # Tool succeeded - just show brief confirmation
                            print("   [Done]", flush=True)

        print("\n" + "-" * 70 + "\n")
        return "continue", response_text

    except Exception as e:
        error_str = str(e)
        print(f"\nError during agent session: {error_str}")
        
        # Check if this is a rate limit error
        wait_time = parse_rate_limit_error(error_str)
        if wait_time is not None:
            return "rate_limited", str(wait_time)
        
        return "error", error_str


async def handle_rate_limit(wait_seconds: int) -> None:
    """
    Handle rate limit by waiting with progress display.
    
    Args:
        wait_seconds: Number of seconds to wait
    """
    print("\n" + "=" * 70)
    print("  ⏳ RATE LIMITED - Pro subscription quota reached")
    print("=" * 70)
    print(f"\nWaiting {format_wait_time(wait_seconds)} before resuming...")
    print("(The agent will automatically continue after the wait)")
    print()
    
    # Show countdown every minute for long waits, every 10 seconds for short
    update_interval = 60 if wait_seconds > 120 else 10
    
    remaining = wait_seconds
    while remaining > 0:
        wait_chunk = min(update_interval, remaining)
        await asyncio.sleep(wait_chunk)
        remaining -= wait_chunk
        if remaining > 0:
            print(f"  ... {format_wait_time(remaining)} remaining", flush=True)
    
    print("\n✓ Wait complete! Resuming agent...\n")


async def run_autonomous_agent(
    project_dir: Path,
    planning_model: str,
    coding_model: str,
    max_iterations: Optional[int] = None,
    spec_file: Optional[str] = None,
) -> None:
    """
    Run the autonomous agent loop with hybrid model support.

    Args:
        project_dir: Directory for the project
        planning_model: Claude model for initialization/planning (e.g., Opus)
        coding_model: Claude model for implementation (e.g., Sonnet)
        max_iterations: Maximum number of iterations (None for unlimited)
        spec_file: Optional custom spec file name (e.g., "nvmercantile_spec.txt")
    """
    # Check if using hybrid mode
    is_hybrid = planning_model != coding_model
    
    print("\n" + "=" * 70)
    print("  AUTONOMOUS CODING AGENT")
    print("=" * 70)
    print(f"\nProject directory: {project_dir}")
    
    if is_hybrid:
        print(f"\n🎯 HYBRID MODE:")
        print(f"   Planning model:  {planning_model}")
        print(f"   Coding model:    {coding_model}")
    else:
        print(f"Model: {planning_model}")
    
    if max_iterations:
        print(f"Max iterations: {max_iterations}")
    else:
        print("Max iterations: Unlimited (will run until completion)")
    print("\n💡 Rate limit handling: ENABLED")
    print("   Agent will auto-wait and resume if Pro quota is exceeded")
    print()

    # Create project directory
    project_dir.mkdir(parents=True, exist_ok=True)

    # Check if this is a fresh start or continuation
    tests_file = project_dir / "feature_list.json"
    is_first_run = not tests_file.exists()

    if is_first_run:
        print("Fresh start - will use initializer agent")
        print()
        print("=" * 70)
        print("  NOTE: First session takes 10-20+ minutes!")
        print("  The agent is generating 200 detailed test cases.")
        print("  This may appear to hang - it's working. Watch for [Tool: ...] output.")
        print("=" * 70)
        print()
        # Copy the app spec into the project directory for the agent to read
        copy_spec_to_project(project_dir, spec_file)
    else:
        print("Continuing existing project")
        print_progress_summary(project_dir)

    # Main loop
    iteration = 0
    rate_limit_retries = 0
    last_wait_used_fallback = False  # Track if previous wait used fallback (no header)

    while True:
        iteration += 1

        # Check max iterations
        if max_iterations and iteration > max_iterations:
            print(f"\nReached max iterations ({max_iterations})")
            print("To continue, run the script again without --max-iterations")
            break

        # Print session header
        print_session_header(iteration, is_first_run)

        # Choose prompt and model based on session type
        if is_first_run:
            prompt = get_initializer_prompt()
            current_model = planning_model
            if is_hybrid:
                print(f"📋 Using planning model: {planning_model}")
            is_first_run = False  # Only use initializer once
        else:
            prompt = get_coding_prompt()
            current_model = coding_model

        # Create client (fresh context) with appropriate model
        client = create_client(project_dir, current_model)

        # Run session with async context manager
        async with client:
            status, response = await run_agent_session(client, prompt, project_dir)

        # Handle status
        if status == "continue":
            rate_limit_retries = 0  # Reset retry counter on success
            last_wait_used_fallback = False  # Reset fallback tracking on success
            print(f"\nAgent will auto-continue in {AUTO_CONTINUE_DELAY_SECONDS}s...")
            print_progress_summary(project_dir)
            await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)

        elif status == "rate_limited":
            rate_limit_retries += 1
            
            if rate_limit_retries > RATE_LIMIT_RETRY_COUNT:
                print("\n❌ Too many rate limit retries. Stopping agent.")
                print("   Try again later or upgrade your subscription.")
                break
            
            # Try to parse wait time from response (retry-after header)
            # If not found, use fallback: 5 hours first, 24 hours if throttled again immediately
            try:
                wait_seconds = int(response)
                used_fallback = False
                print(f"\n⚠️  Rate limit hit - waiting {format_wait_time(wait_seconds)} (from header)")
            except (ValueError, TypeError):
                wait_seconds = get_fallback_wait_time(last_wait_used_fallback)
                used_fallback = True
                if last_wait_used_fallback:
                    print(f"\n⚠️  Rate limit hit again after fallback wait - extended wait: {format_wait_time(wait_seconds)}")
                else:
                    print(f"\n⚠️  Rate limit hit (no header) - fallback wait: {format_wait_time(wait_seconds)}")
            
            print(f"   (attempt {rate_limit_retries}/{RATE_LIMIT_RETRY_COUNT})")
            
            # Handle the rate limit wait
            await handle_rate_limit(wait_seconds)
            
            # Track whether this wait used fallback for next iteration
            last_wait_used_fallback = used_fallback
            
            # Don't increment iteration - we want to retry the same work
            iteration -= 1

        elif status == "error":
            print("\nSession encountered an error")
            print("Will retry with a fresh session...")
            await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)

        # Small delay between sessions
        if max_iterations is None or iteration < max_iterations:
            print("\nPreparing next session...\n")
            await asyncio.sleep(1)

    # Final summary
    print("\n" + "=" * 70)
    print("  SESSION COMPLETE")
    print("=" * 70)
    print(f"\nProject directory: {project_dir}")
    print_progress_summary(project_dir)

    # Print instructions for running the generated application
    print("\n" + "-" * 70)
    print("  TO RUN THE GENERATED APPLICATION:")
    print("-" * 70)
    print(f"\n  cd {project_dir.resolve()}")
    print("  ./init.sh           # Run the setup script")
    print("  # Or manually:")
    print("  npm install && npm run dev")
    print("\n  Then open http://localhost:5173")
    print("-" * 70)

    print("\nDone!")
