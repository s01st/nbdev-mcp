"""Tests for nbdev_mcp.utils.md module."""

import pytest

from nbdev_mcp.utils.md import (
    extract_references,
    refs_used,
    clear_section_buffer,
    group_lines_by_sections,
    readd_reference_links,
    split_markdown_into_cells,
)


class TestExtractReferences:
    """Test reference link extraction."""

    def test_extract_references_basic(self):
        """Test extracting reference definitions."""
        lines = ["Hello [world][1]", "", "[1]: https://example.com"]
        text, refs = extract_references(lines)
        assert len(text) == 2
        assert "1" in refs
        assert "[1]: https://example.com" in refs["1"]

    def test_extract_references_no_refs(self):
        """Test with no reference definitions."""
        lines = ["Hello world", "No refs here"]
        text, refs = extract_references(lines)
        assert len(text) == 2
        assert len(refs) == 0

    def test_extract_references_multiple(self):
        """Test extracting multiple references."""
        lines = ["[a]: url1", "[b]: url2", "text"]
        text, refs = extract_references(lines)
        assert len(text) == 1
        assert "a" in refs
        assert "b" in refs


class TestRefsUsed:
    """Test reference usage detection."""

    def test_refs_used_bracket_bracket(self):
        """Test [text][id] pattern detection."""
        ref_defs = {"1": "[1]: url"}
        result = refs_used("See [link][1] here", ref_defs)
        assert "1" in result

    def test_refs_used_bare_bracket(self):
        """Test bare [id] pattern detection."""
        ref_defs = {"link": "[link]: url"}
        result = refs_used("See [link] here", ref_defs)
        assert "link" in result

    def test_refs_used_not_in_defs(self):
        """Test that undefined refs are not matched."""
        ref_defs = {"a": "[a]: url"}
        result = refs_used("See [b] here", ref_defs)
        assert "b" not in result


class TestClearSectionBuffer:
    """Test section buffer clearing."""

    def test_clear_section_buffer_with_content(self):
        """Test clearing buffer with content."""
        cell_strs = ["existing"]
        buffer = ["line1", "line2"]
        result_cells, result_buffer = clear_section_buffer(cell_strs, buffer)
        assert len(result_cells) == 2
        assert "line1\nline2" in result_cells[-1]
        assert len(result_buffer) == 0

    def test_clear_section_buffer_empty(self):
        """Test clearing empty buffer."""
        cell_strs = ["existing"]
        buffer = []
        result_cells, result_buffer = clear_section_buffer(cell_strs, buffer)
        assert len(result_cells) == 1
        assert len(result_buffer) == 0


class TestGroupLinesBySections:
    """Test markdown section grouping."""

    def test_group_lines_basic(self):
        """Test basic section grouping."""
        lines = ["# Title", "Some text", "## Section", "More text"]
        result = group_lines_by_sections(lines)
        assert len(result) == 4
        assert result[0] == "# Title"
        assert result[2] == "## Section"

    def test_group_lines_consecutive_headers(self):
        """Test consecutive headers."""
        lines = ["# H1", "## H2", "### H3"]
        result = group_lines_by_sections(lines)
        assert len(result) == 3

    def test_group_lines_no_headers(self):
        """Test content without headers."""
        lines = ["Just text", "More text"]
        result = group_lines_by_sections(lines)
        assert len(result) == 1
        assert "Just text" in result[0]


class TestReaddReferenceLinks:
    """Test reference link re-adding."""

    def test_readd_reference_links_basic(self):
        """Test adding refs to cells that use them."""
        cells_raw = ["See [link][1]"]
        ref_defs = {"1": "[1]: https://example.com"}
        result = readd_reference_links(cells_raw, ref_defs)
        assert len(result) == 1
        assert result[0]["cell_type"] == "markdown"
        assert "[1]: https://example.com" in result[0]["source"]

    def test_readd_reference_links_no_refs(self):
        """Test cells without references."""
        cells_raw = ["No refs here"]
        ref_defs = {"1": "[1]: url"}
        result = readd_reference_links(cells_raw, ref_defs)
        assert "[1]:" not in result[0]["source"]


class TestSplitMarkdownIntoCells:
    """Test full markdown splitting."""

    def test_split_markdown_into_cells_basic(self):
        """Test basic markdown splitting."""
        md = """# Title

Some intro text.

## Section 1

Content here.
"""
        cells = split_markdown_into_cells(md)
        assert len(cells) >= 3
        assert all(c["cell_type"] == "markdown" for c in cells)

    def test_split_markdown_with_refs(self):
        """Test splitting markdown with references."""
        md = """# Title

See [link][1] for details.

[1]: https://example.com
"""
        cells = split_markdown_into_cells(md)
        # The ref should be appended to cells that use it
        cell_sources = [c["source"] for c in cells]
        has_ref = any("[1]:" in s for s in cell_sources)
        assert has_ref

    def test_split_markdown_empty(self):
        """Test splitting empty markdown."""
        cells = split_markdown_into_cells("")
        assert isinstance(cells, list)
