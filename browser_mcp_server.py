#!/usr/bin/env python3
"""
Browser MCP Server for Visual Testing
======================================

A Model Context Protocol (MCP) server that wraps the browser-use-demo's
Playwright-based browser automation for visual testing in the autonomous
coding agent.

Usage:
    python browser_mcp_server.py

This server exposes browser automation tools via stdio MCP protocol.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# Add browser-use-demo to path
BROWSER_USE_DEMO_PATH = Path(__file__).parent.parent / "browser-use-demo"
sys.path.insert(0, str(BROWSER_USE_DEMO_PATH))

from browser_use_demo.tools.browser import BrowserTool, BROWSER_TOOL_INPUT_SCHEMA


class BrowserMCPServer:
    """
    MCP Server that wraps BrowserTool for Claude Code SDK integration.
    
    Communicates via stdio using JSON-RPC 2.0 protocol.
    """
    
    def __init__(self):
        self.browser_tool = BrowserTool()
        self.running = True
    
    async def handle_request(self, request: dict) -> dict:
        """Handle a single JSON-RPC request."""
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")
        
        try:
            if method == "initialize":
                return self._make_response(request_id, {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "browser-visual-testing",
                        "version": "1.0.0"
                    },
                    "capabilities": {
                        "tools": {}
                    }
                })
            
            elif method == "tools/list":
                return self._make_response(request_id, {
                    "tools": [
                        {
                            "name": "browser_visual_test",
                            "description": self._get_tool_description(),
                            "inputSchema": self._get_input_schema()
                        }
                    ]
                })
            
            elif method == "tools/call":
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})
                
                if tool_name == "browser_visual_test":
                    result = await self._execute_browser_action(tool_args)
                    return self._make_response(request_id, {
                        "content": result
                    })
                else:
                    return self._make_error(request_id, -32601, f"Unknown tool: {tool_name}")
            
            elif method == "notifications/initialized":
                # Notification, no response needed
                return None
            
            else:
                return self._make_error(request_id, -32601, f"Method not found: {method}")
                
        except Exception as e:
            return self._make_error(request_id, -32000, str(e))
    
    def _make_response(self, request_id: Any, result: dict) -> dict:
        """Create a JSON-RPC success response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result
        }
    
    def _make_error(self, request_id: Any, code: int, message: str) -> dict:
        """Create a JSON-RPC error response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message
            }
        }
    
    def _get_tool_description(self) -> str:
        """Get the tool description for visual testing."""
        return """Browser automation tool for visual testing of web applications.

Key actions for visual testing:
- navigate: Go to a URL (automatically captures screenshot)
- screenshot: Take a viewport screenshot
- zoom: Take a zoomed screenshot of a specific region
- read_page: Get DOM structure with element refs for analysis
- scroll: Scroll and capture new viewport
- set_viewport: Change viewport size for responsive testing

Mouse/Keyboard actions:
- left_click, right_click, double_click: Click elements
- type: Enter text
- key: Press key combinations
- form_input: Fill form fields

Use this for:
1. Visual verification of UI elements
2. Responsive design testing (mobile, tablet, desktop viewports)
3. End-to-end user flow testing
4. Screenshot comparison
"""
    
    def _get_input_schema(self) -> dict:
        """Get the input schema, extending the base schema with viewport control."""
        schema = BROWSER_TOOL_INPUT_SCHEMA.copy()
        
        # Add viewport setting for responsive testing
        schema["properties"]["viewport"] = {
            "description": "Set viewport size for responsive testing. Format: [width, height]. Common sizes: [375, 667] (iPhone SE), [768, 1024] (iPad), [1920, 1080] (Desktop)",
            "type": "array",
            "items": {"type": "integer"}
        }
        
        # Add set_viewport action
        if "enum" in schema["properties"]["action"]:
            schema["properties"]["action"]["enum"].append("set_viewport")
            schema["properties"]["action"]["description"] += '\n* `set_viewport`: Change the browser viewport size for responsive testing (requires viewport parameter).'
        
        return schema
    
    async def _execute_browser_action(self, args: dict) -> list:
        """Execute a browser action and return MCP-formatted content."""
        action = args.get("action", "screenshot")
        
        try:
            # Handle viewport resize for responsive testing
            if action == "set_viewport":
                viewport = args.get("viewport", [1920, 1080])
                if len(viewport) >= 2:
                    await self._set_viewport(viewport[0], viewport[1])
                    return [{
                        "type": "text",
                        "text": f"Viewport set to {viewport[0]}x{viewport[1]}"
                    }]
            
            # Call the browser tool
            result = await self.browser_tool(
                action=action,
                text=args.get("text"),
                ref=args.get("ref"),
                coordinate=args.get("coordinate"),
                start_coordinate=args.get("start_coordinate"),
                scroll_direction=args.get("scroll_direction"),
                scroll_amount=args.get("scroll_amount"),
                duration=args.get("duration"),
                value=args.get("value"),
                region=args.get("region"),
            )
            
            content = []
            
            # Add text output if present
            if result.output:
                content.append({
                    "type": "text",
                    "text": result.output
                })
            
            # Add image if present
            if result.base64_image:
                content.append({
                    "type": "image",
                    "data": result.base64_image,
                    "mimeType": "image/png"
                })
            
            # Add error if present
            if result.error:
                content.append({
                    "type": "text",
                    "text": f"Error: {result.error}"
                })
            
            return content if content else [{"type": "text", "text": "Action completed"}]
            
        except Exception as e:
            return [{
                "type": "text",
                "text": f"Browser action failed: {str(e)}"
            }]
    
    async def _set_viewport(self, width: int, height: int):
        """Set the browser viewport size for responsive testing."""
        # Ensure browser is initialized
        await self.browser_tool._ensure_browser()
        
        if self.browser_tool._page:
            await self.browser_tool._page.set_viewport_size({
                "width": width,
                "height": height
            })
            # Update tool dimensions
            self.browser_tool.width = width
            self.browser_tool.height = height
    
    async def run(self):
        """Run the MCP server, reading from stdin and writing to stdout."""
        print("[BrowserMCP] Server starting...", file=sys.stderr)
        
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        
        while self.running:
            try:
                # Read line from stdin
                line = await reader.readline()
                if not line:
                    break
                
                line = line.decode('utf-8').strip()
                if not line:
                    continue
                
                # Parse JSON-RPC request
                try:
                    request = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                # Handle request
                response = await self.handle_request(request)
                
                # Send response (if not a notification)
                if response is not None:
                    response_line = json.dumps(response) + "\n"
                    sys.stdout.write(response_line)
                    sys.stdout.flush()
                    
            except Exception as e:
                print(f"[BrowserMCP] Error: {e}", file=sys.stderr)
                continue
        
        print("[BrowserMCP] Server stopped", file=sys.stderr)
    
    async def cleanup(self):
        """Clean up browser resources."""
        self.running = False
        if hasattr(self.browser_tool, '_browser') and self.browser_tool._browser:
            await self.browser_tool._browser.close()
        if hasattr(self.browser_tool, '_playwright') and self.browser_tool._playwright:
            await self.browser_tool._playwright.stop()


async def main():
    """Main entry point."""
    server = BrowserMCPServer()
    try:
        await server.run()
    finally:
        await server.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
