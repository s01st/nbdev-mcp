"""MCP integration tests for nbdev-mcp server.

These tests verify that the MCP server properly exposes tools, resources,
and prompts through the FastMCP interface. Tests use in-memory async calls
directly to FastMCP without subprocess overhead.

References:
- FastMCP testing patterns: https://gofastmcp.com/patterns/testing
- MCP SDK: https://github.com/modelcontextprotocol/python-sdk
"""

import pytest
from pathlib import Path
import json

from nbdev_mcp.mcp import create_nbdev_mcp
import nbdev_mcp.utils.config as config_module


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mcp_server():
    """Create a fresh MCP server instance for testing."""
    return create_nbdev_mcp()


@pytest.fixture
def temp_nbdev_project(tmp_path: Path) -> Path:
    """Create a temporary nbdev project for tool testing."""
    # Create directories
    (tmp_path / "nbs").mkdir()
    (tmp_path / "mylib").mkdir()
    (tmp_path / "mylib" / "__init__.py").write_text("")

    # Create settings.ini
    settings = tmp_path / "settings.ini"
    settings.write_text("""[DEFAULT]
lib_name = mylib
lib_path = mylib
nbs_path = nbs
version = 0.0.1
""")

    # Create a sample notebook
    nb_data = {
        "cells": [
            {
                "cell_type": "code",
                "source": ["#| default_exp core"],
                "metadata": {},
                "outputs": [],
                "execution_count": None
            },
            {
                "cell_type": "markdown",
                "source": ["# Core Module\n", "\n", "Main functionality."],
                "metadata": {}
            },
            {
                "cell_type": "code",
                "source": ["#| export\n", "def greet(name: str) -> str:\n", "    '''Greet someone.'''\n", "    return f'Hello, {name}!'"],
                "metadata": {},
                "outputs": [],
                "execution_count": None
            }
        ],
        "metadata": {
            "kernelspec": {"display_name": "python3", "language": "python", "name": "python3"}
        },
        "nbformat": 4,
        "nbformat_minor": 5
    }

    nb_path = tmp_path / "nbs" / "00_core.ipynb"
    nb_path.write_text(json.dumps(nb_data, indent=2))

    return tmp_path


@pytest.fixture
async def mcp_with_project(mcp_server, temp_nbdev_project):
    """MCP server with a project already selected via MCP tool."""
    import nbdev_mcp.utils.paths as paths_module

    # Set project through the MCP tool
    await mcp_server.call_tool("set_project", {"selector": str(temp_nbdev_project)})

    # WORKAROUND: Also update paths.CURRENT_PROJECT directly
    # The set_project tool only updates config.CURRENT_PROJECT, but paths.py
    # imports CURRENT_PROJECT by value at module load time, creating a separate binding.
    # This is a known architectural issue - paths.py should use get_current_project().
    paths_module.CURRENT_PROJECT = temp_nbdev_project

    yield mcp_server

    # Clean up - reset both modules
    paths_module.CURRENT_PROJECT = None
    config_module.CURRENT_PROJECT = None


# =============================================================================
# Tool Listing Tests
# =============================================================================


class TestListTools:
    """Tests for MCP tool listing functionality."""

    async def test_list_tools_returns_list(self, mcp_server):
        """list_tools() should return a list of Tool objects."""
        tools = await mcp_server.list_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0

    async def test_list_tools_has_expected_count(self, mcp_server):
        """Server should expose the expected number of tools."""
        tools = await mcp_server.list_tools()
        # We expect at least 40+ tools based on our implementation
        assert len(tools) >= 40, f"Expected at least 40 tools, got {len(tools)}"

    async def test_list_tools_has_required_tools(self, mcp_server):
        """Server should have core required tools."""
        tools = await mcp_server.list_tools()
        tool_names = {t.name for t in tools}

        required_tools = {
            # Project management
            "set_project",
            "current_project",
            "find_projects",
            "bookmark_project",
            "list_bookmarks",
            # Environment
            "ensure_env",
            "export_env",
            # nbdev commands
            "nbdev_prepare",
            "nbdev_export",
            "nbdev_test",
            # Notebook editing
            "check_if_generated",
            "find_source_notebook",
            "analyze_exports",
            "read_notebook_cell",
            "edit_notebook_cell",
            "add_notebook_cell",
            # Lint tools
            "validate_inits",
            "lint_rules",
            "lint_main_guards",
            # Analysis tools
            "modidx_audit",
            "find_symbol",
            "analyze_dependency_order",
            # Test tools
            "pytest_run",
            "run_tutorials",
            "scan_notebook_errors",
        }

        missing = required_tools - tool_names
        assert not missing, f"Missing required tools: {missing}"

    async def test_tools_have_descriptions(self, mcp_server):
        """All tools should have descriptions."""
        tools = await mcp_server.list_tools()
        for tool in tools:
            assert tool.description, f"Tool {tool.name} missing description"


# =============================================================================
# Resource Listing Tests
# =============================================================================


class TestListResources:
    """Tests for MCP resource listing functionality."""

    async def test_list_resources_returns_list(self, mcp_server):
        """list_resources() should return a list."""
        resources = await mcp_server.list_resources()
        assert isinstance(resources, list)

    async def test_list_resources_has_expected_resources(self, mcp_server):
        """Server should expose expected resources."""
        resources = await mcp_server.list_resources()
        # Convert AnyUrl objects to strings for comparison
        resource_uris = {str(r.uri) for r in resources}

        expected_uris = {
            "nbdev://project",
            "nbdev://projects",
            "nbdev://tree",
            "nbdev://roadmap",
            "nbdev://settings",
        }

        for uri in expected_uris:
            assert uri in resource_uris, f"Missing resource: {uri}"

    async def test_resources_have_names(self, mcp_server):
        """All resources should have names."""
        resources = await mcp_server.list_resources()
        for resource in resources:
            assert resource.name, f"Resource {resource.uri} missing name"


# =============================================================================
# Prompt Listing Tests
# =============================================================================


class TestListPrompts:
    """Tests for MCP prompt listing functionality."""

    async def test_list_prompts_returns_list(self, mcp_server):
        """list_prompts() should return a list."""
        prompts = await mcp_server.list_prompts()
        assert isinstance(prompts, list)

    async def test_list_prompts_has_expected_count(self, mcp_server):
        """Server should expose expected number of prompts."""
        prompts = await mcp_server.list_prompts()
        # We expect multiple philosophy/guidance prompts
        assert len(prompts) >= 5, f"Expected at least 5 prompts, got {len(prompts)}"

    async def test_list_prompts_has_required_prompts(self, mcp_server):
        """Server should have core required prompts."""
        prompts = await mcp_server.list_prompts()
        prompt_names = {p.name for p in prompts}

        required_prompts = {
            "nbdev_workflow_philosophy",
            "nbdev_principles",
            "documentation_best_practices",
        }

        missing = required_prompts - prompt_names
        assert not missing, f"Missing required prompts: {missing}"

    async def test_prompts_have_descriptions(self, mcp_server):
        """All prompts should have descriptions."""
        prompts = await mcp_server.list_prompts()
        for prompt in prompts:
            assert prompt.description, f"Prompt {prompt.name} missing description"


# =============================================================================
# Tool Execution Tests
# =============================================================================


class TestCallTools:
    """Tests for MCP tool execution functionality."""

    async def test_find_projects_tool(self, mcp_server, tmp_path):
        """find_projects tool should work without a project selected."""
        result = await mcp_server.call_tool("find_projects", {"roots": [str(tmp_path)]})
        # Result should be a list of content items
        assert result is not None

    async def test_set_project_tool(self, mcp_server, temp_nbdev_project):
        """set_project tool should set the current project."""
        result = await mcp_server.call_tool(
            "set_project",
            {"selector": str(temp_nbdev_project)}
        )
        assert result is not None
        # Clean up
        import nbdev_mcp.utils.paths as paths_module
        paths_module.CURRENT_PROJECT = None
        config_module.CURRENT_PROJECT = None

    async def test_current_project_requires_project(self, mcp_server, tmp_path):
        """current_project should error when cwd is not an nbdev project."""
        import os
        import nbdev_mcp.utils.paths as paths_module

        # Ensure no project is explicitly set
        paths_module.CURRENT_PROJECT = None
        config_module.CURRENT_PROJECT = None

        # Change to a non-nbdev directory to test the error case
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with pytest.raises(Exception) as exc_info:
                await mcp_server.call_tool("current_project", {})
            assert "not an nbdev project" in str(exc_info.value)
        finally:
            os.chdir(original_cwd)

    async def test_current_project_with_project(self, mcp_with_project):
        """current_project should return info when project is set."""
        result = await mcp_with_project.call_tool("current_project", {})
        assert result is not None

    async def test_analyze_exports_tool(self, mcp_with_project, temp_nbdev_project):
        """analyze_exports should analyze notebook exports."""
        nb_path = temp_nbdev_project / "nbs" / "00_core.ipynb"
        result = await mcp_with_project.call_tool(
            "analyze_exports",
            {"notebook": str(nb_path)}
        )
        assert result is not None

    async def test_read_notebook_cell_tool(self, mcp_with_project, temp_nbdev_project):
        """read_notebook_cell should read specific cells."""
        nb_path = temp_nbdev_project / "nbs" / "00_core.ipynb"
        result = await mcp_with_project.call_tool(
            "read_notebook_cell",
            {"notebook": str(nb_path), "cell_index": 0}
        )
        assert result is not None

    async def test_read_notebook_cell_truncates(self, mcp_with_project, temp_nbdev_project):
        """read_notebook_cell should truncate large cells."""
        nb_path = temp_nbdev_project / "nbs" / "01_big.ipynb"
        big_source = ["#| export\n", "x = '" + ("a" * 5000) + "'\n"]
        nb_data = {
            "cells": [
                {"cell_type": "code", "source": big_source, "metadata": {}, "outputs": [], "execution_count": None}
            ],
            "metadata": {
                "kernelspec": {"display_name": "python3", "language": "python", "name": "python3"}
            },
            "nbformat": 4,
            "nbformat_minor": 5
        }
        nb_path.write_text(json.dumps(nb_data, indent=2))
        result = await mcp_with_project.call_tool(
            "read_notebook_cell",
            {"notebook": str(nb_path), "cell_index": 0, "truncate_length": 200}
        )
        payload = result[1]["result"] if isinstance(result, tuple) else result
        assert payload["ok"] is True
        assert payload["truncated"] is True
        assert payload["source_length"] > 200

    async def test_check_if_generated_tool(self, mcp_with_project, temp_nbdev_project):
        """check_if_generated should check for auto-generated files."""
        py_file = temp_nbdev_project / "mylib" / "__init__.py"
        result = await mcp_with_project.call_tool(
            "check_if_generated",
            {"file_path": str(py_file)}
        )
        assert result is not None

    async def test_validate_inits_tool(self, mcp_with_project):
        """validate_inits should check init notebooks."""
        result = await mcp_with_project.call_tool("validate_inits", {})
        assert result is not None

    async def test_lint_rules_tool(self, mcp_with_project):
        """lint_rules should lint notebooks."""
        result = await mcp_with_project.call_tool("lint_rules", {})
        assert result is not None


# =============================================================================
# Resource Read Tests
# =============================================================================


class TestReadResources:
    """Tests for MCP resource reading functionality."""

    async def test_read_projects_resource(self, mcp_server):
        """Should read the projects resource."""
        result = await mcp_server.read_resource("nbdev://projects")
        assert result is not None

    async def test_read_project_resource_requires_project(self, mcp_server):
        """project resource should handle missing project gracefully."""
        import nbdev_mcp.utils.paths as paths_module
        paths_module.CURRENT_PROJECT = None
        config_module.CURRENT_PROJECT = None
        # This may return empty or raise - either is acceptable
        try:
            result = await mcp_server.read_resource("nbdev://project")
            # If it doesn't raise, it should return something
            assert result is not None
        except Exception:
            # Raising is also acceptable behavior
            pass

    async def test_read_project_resource_with_project(self, mcp_with_project):
        """project resource should return project info when set."""
        result = await mcp_with_project.read_resource("nbdev://project")
        assert result is not None


# =============================================================================
# Prompt Get Tests
# =============================================================================


class TestGetPrompts:
    """Tests for MCP prompt retrieval functionality."""

    async def test_get_workflow_philosophy_prompt(self, mcp_server):
        """Should retrieve the workflow philosophy prompt."""
        result = await mcp_server.get_prompt("nbdev_workflow_philosophy")
        assert result is not None
        assert result.messages is not None
        assert len(result.messages) > 0

    async def test_get_nbdev_principles_prompt(self, mcp_server):
        """Should retrieve the nbdev principles prompt."""
        result = await mcp_server.get_prompt("nbdev_principles")
        assert result is not None
        assert result.messages is not None

    async def test_get_documentation_best_practices_prompt(self, mcp_server):
        """Should retrieve the documentation best practices prompt."""
        result = await mcp_server.get_prompt("documentation_best_practices")
        assert result is not None
        assert result.messages is not None

    async def test_prompt_content_is_not_empty(self, mcp_server):
        """Prompt content should not be empty."""
        result = await mcp_server.get_prompt("nbdev_principles")
        assert result.messages[0].content is not None
        # Content should have meaningful length
        content = str(result.messages[0].content)
        assert len(content) > 100, f"Prompt content too short: {len(content)} chars"


# =============================================================================
# Server Creation Tests
# =============================================================================


class TestServerCreation:
    """Tests for MCP server creation and configuration."""

    def test_create_server_returns_fastmcp(self):
        """create_nbdev_mcp should return a FastMCP instance."""
        from mcp.server.fastmcp import FastMCP
        mcp = create_nbdev_mcp()
        assert isinstance(mcp, FastMCP)

    def test_create_server_has_name(self):
        """Server should have the expected name."""
        mcp = create_nbdev_mcp()
        assert mcp.name == "mcp.nbdev"

    def test_create_server_custom_name(self):
        """Server should accept custom name."""
        mcp = create_nbdev_mcp(name="custom.server")
        assert mcp.name == "custom.server"
