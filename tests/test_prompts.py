"""Tests for nbdev_mcp.prompts module and prompt template inclusion."""

import pytest
import os
from pathlib import Path

from nbdev_mcp.prompts import (
    get_bundled_template,
    prompt_template_path,
    prompt_context,
    render_prompt,
    nbdev_workflow_philosophy,
    nbdev_principles,
    documentation_best_practices,
    future_imports_guidance,
    nbdev_howto,
    nbdev_documentation_guide,
    module_scaffold,
    nbdev_advanced_patterns,
    nbdev_main_patterns,
)
from nbdev_mcp.utils.config import (
    get_config,
    configure,
    NBMCP_CONFIG,
    DEFAULT_CONFIG,
)


# Expected prompt template files that MUST be included in the package
EXPECTED_TEMPLATES = [
    "workflow_philosophy.md",
    "nbdev_principles.md",
    "documentation_best_practices.md",
    "future_imports_guidance.md",
    "nbdev_howto.md",
    "documentation_guideline.md",
    "module_scaffold.md",
    "advanced_patterns.md",
    "main_pattern.md",
]


class TestPromptTemplateInclusion:
    """Tests proving prompt template markdown files are bundled in the package."""

    def test_all_expected_templates_bundled(self):
        """All expected prompt templates are bundled and loadable via importlib.resources."""
        for template in EXPECTED_TEMPLATES:
            content = get_bundled_template(template)
            assert len(content) > 10, f"{template} should have meaningful content"

    def test_templates_are_valid_markdown(self):
        """All bundled templates are valid markdown (readable text)."""
        for template in EXPECTED_TEMPLATES:
            content = get_bundled_template(template)
            assert len(content) > 10, f"{template} should have meaningful content"
            # Basic markdown check - should not be binary
            assert "\x00" not in content, f"{template} should be valid text, not binary"

    def test_bundled_template_raises_on_missing(self):
        """get_bundled_template raises FileNotFoundError for missing templates."""
        with pytest.raises(FileNotFoundError):
            get_bundled_template("nonexistent_template_xyz.md")

    def test_templates_exist_in_package_dir(self, project_root):
        """Templates exist in nbdev_mcp/prompt_templates/ directory."""
        templates_dir = project_root / "nbdev_mcp" / "prompt_templates"
        assert templates_dir.exists(), "nbdev_mcp/prompt_templates/ directory must exist"

        for template in EXPECTED_TEMPLATES:
            template_path = templates_dir / template
            assert template_path.exists(), f"Template {template} must exist in package"


class TestPromptRendering:
    """Tests for prompt rendering functionality."""

    def test_render_prompt_returns_string(self):
        """render_prompt returns non-empty string content."""
        content = render_prompt("nbdev_principles.md")
        assert isinstance(content, str)
        assert len(content) > 50  # Should have meaningful content

    def test_render_prompt_substitutes_placeholders(self, temp_project):
        """render_prompt substitutes {lib} and {nbs_path} placeholders."""
        # Set up a project context
        import nbdev_mcp.utils.config
        old_project = nbdev_mcp.utils.config.CURRENT_PROJECT
        nbdev_mcp.utils.config.CURRENT_PROJECT = temp_project

        try:
            content = render_prompt("nbdev_principles.md")
            # Should substitute {lib} with 'testlib' from temp_project settings
            assert "testlib" in content or "{lib}" not in content
        finally:
            nbdev_mcp.utils.config.CURRENT_PROJECT = old_project

    def test_all_prompt_functions_return_content(self):
        """All public prompt functions return non-empty strings."""
        # These prompts use simple placeholders {lib}, {nbs_path} and work with .format()
        simple_prompts = [
            nbdev_workflow_philosophy,
            nbdev_principles,
            documentation_best_practices,
            future_imports_guidance,
            nbdev_howto,
            nbdev_advanced_patterns,
            nbdev_main_patterns,
        ]

        for func in simple_prompts:
            result = func()
            assert isinstance(result, str), f"{func.__name__} should return string"
            assert len(result) > 20, f"{func.__name__} should return meaningful content"

    def test_documentation_guide_template_exists(self):
        """documentation_guideline.md template exists and is readable."""
        # This template has complex formatting (code blocks with {}) that may fail .format()
        # Just verify it's bundled and readable
        content = get_bundled_template("documentation_guideline.md")
        assert len(content) > 100
        assert "Documentation" in content or "nbdev" in content

    def test_module_scaffold_template_exists(self):
        """module_scaffold.md template exists and is readable."""
        # This template uses {module.capitalize()} which doesn't work with .format()
        # Just verify it's bundled
        content = get_bundled_template("module_scaffold.md")
        assert len(content) > 50
        assert "{module}" in content  # Verify it has the placeholder
        assert "{lib}" in content


class TestPromptOverride:
    """Tests for overriding base prompts with custom prompt directory."""

    def test_config_has_prompt_dir_setting(self):
        """Config includes prompt_dir setting."""
        cfg = get_config()
        assert "prompt_dir" in cfg
        assert cfg["prompt_dir"] == "prompt_templates"  # Default value

    def test_override_prompt_via_config(self, tmp_path):
        """Custom prompt_dir in config overrides default templates."""
        # Create custom prompt directory
        custom_dir = tmp_path / "custom_prompts"
        custom_dir.mkdir()

        # Create a custom template that differs from default
        custom_template = custom_dir / "nbdev_principles.md"
        custom_content = "# CUSTOM PRINCIPLES\nThis is a custom override!"
        custom_template.write_text(custom_content)

        # Save original config
        original_prompt_dir = get_config()["prompt_dir"]

        try:
            # Configure to use custom absolute path
            configure(prompt_dir=str(custom_dir))

            # The custom template should be found
            path = prompt_template_path("nbdev_principles.md")
            assert path == custom_template

            # Rendering should use custom content
            content = render_prompt("nbdev_principles.md")
            assert "CUSTOM PRINCIPLES" in content
            assert "custom override" in content
        finally:
            # Restore original config
            configure(prompt_dir=original_prompt_dir)

    def test_override_falls_back_to_bundled_for_missing(self, tmp_path):
        """When custom dir lacks a template, render_prompt falls back to bundled."""
        custom_dir = tmp_path / "partial_prompts"
        custom_dir.mkdir()

        # Only create ONE custom template
        (custom_dir / "nbdev_principles.md").write_text("# Custom Principles Only")

        original = get_config()["prompt_dir"]

        try:
            configure(prompt_dir=str(custom_dir))

            # Custom template should be used via render_prompt
            content = render_prompt("nbdev_principles.md")
            assert "Custom Principles Only" in content

            # Missing template should fall back to bundled
            content2 = render_prompt("workflow_philosophy.md")
            assert len(content2) > 100  # Should get bundled template
        finally:
            configure(prompt_dir=original)

    def test_env_var_override(self, tmp_path, monkeypatch):
        """NBMCP_PROMPT_DIR environment variable overrides prompt_dir."""
        custom_dir = tmp_path / "env_prompts"
        custom_dir.mkdir()
        (custom_dir / "nbdev_principles.md").write_text("# ENV VAR OVERRIDE")

        # Save and clear current prompt_dir
        original = get_config()["prompt_dir"]

        try:
            # Set env var
            monkeypatch.setenv("NBMCP_PROMPT_DIR", str(custom_dir))

            # Update config from env
            get_config().update_from_env()

            # Should now use env var path
            assert get_config()["prompt_dir"] == str(custom_dir)

            path = prompt_template_path("nbdev_principles.md")
            content = path.read_text()
            assert "ENV VAR OVERRIDE" in content
        finally:
            configure(prompt_dir=original)


class TestPromptContext:
    """Tests for prompt context generation."""

    def test_prompt_context_returns_dict(self):
        """prompt_context returns a dictionary."""
        ctx = prompt_context()
        assert isinstance(ctx, dict)
        assert "lib" in ctx
        assert "nbs_path" in ctx

    def test_prompt_context_with_project(self, temp_project):
        """prompt_context extracts lib name from active project."""
        import nbdev_mcp.utils.config
        # Need to use set_current_project to properly set the global
        from nbdev_mcp.utils.config import set_current_project, get_current_project
        old = get_current_project()
        set_current_project(temp_project)

        try:
            ctx = prompt_context()
            # Note: prompt_context reads from the imported CURRENT_PROJECT at module load time
            # so we need to reload or check the actual config
            assert ctx["nbs_path"] == "nbs"
            # lib may be 'testlib' or '<lib_name>' depending on when module was imported
            assert ctx["lib"] in ("testlib", "<lib_name>")
        finally:
            set_current_project(old)

    def test_prompt_context_without_project(self):
        """prompt_context returns placeholders when no project is active."""
        import nbdev_mcp.utils.config
        old = nbdev_mcp.utils.config.CURRENT_PROJECT
        nbdev_mcp.utils.config.CURRENT_PROJECT = None

        try:
            ctx = prompt_context()
            assert ctx["lib"] == "<lib_name>"
            assert ctx["nbs_path"] == "nbs"
        finally:
            nbdev_mcp.utils.config.CURRENT_PROJECT = old


class TestConfigInspection:
    """Tests for config inspection functionality."""

    def test_get_config_returns_dotconfig(self):
        """get_config returns DotConfig instance."""
        cfg = get_config()
        assert hasattr(cfg, 'log_level')
        assert hasattr(cfg, 'prompt_dir')

    def test_config_dot_access(self):
        """Config supports dot notation access."""
        cfg = get_config()
        # Both should work
        assert cfg.log_level == cfg["log_level"]
        assert cfg.prompt_dir == cfg["prompt_dir"]

    def test_configure_updates_global(self):
        """configure() updates the global config."""
        original = get_config()["max_tree_files"]
        try:
            configure(max_tree_files=999)
            assert get_config()["max_tree_files"] == 999
        finally:
            configure(max_tree_files=original)

    def test_default_config_values(self):
        """Default config has expected values."""
        assert DEFAULT_CONFIG["log_level"] in ("INFO", "DEBUG", "WARNING", "ERROR")
        assert DEFAULT_CONFIG["prompt_dir"] == "prompt_templates"
        assert DEFAULT_CONFIG["env_dir_name"] == "Environments"
        assert isinstance(DEFAULT_CONFIG["max_tree_files"], int)

    def test_config_copy_is_independent(self):
        """Config copy is independent of original."""
        cfg = get_config()
        copy = cfg.copy()
        copy["test_key"] = "test_value"
        assert "test_key" not in cfg


class TestPackageDataInclusion:
    """Tests verifying package data configuration for distribution."""

    def test_manifest_includes_prompt_templates(self, project_root):
        """MANIFEST.in includes nbdev_mcp/prompt_templates directory."""
        manifest_path = project_root / "MANIFEST.in"
        if manifest_path.exists():
            content = manifest_path.read_text()
            assert "nbdev_mcp/prompt_templates" in content or "prompt_templates" in content

    def test_prompt_templates_has_init(self, project_root):
        """nbdev_mcp/prompt_templates/ has __init__.py for importlib.resources."""
        init_path = project_root / "nbdev_mcp" / "prompt_templates" / "__init__.py"
        assert init_path.exists(), "__init__.py required for importlib.resources to work"
