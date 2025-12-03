"""Tests for nbdev_mcp.utils.types and nbdev_mcp.utils.rich modules."""
import pytest

from nbdev_mcp.utils.types import (
    ToolResult,
    Issue,
)
from nbdev_mcp.utils.rich import (
    ok_result,
    err_result,
    try_resolve,
    with_project,
    make_console,
    get_output,
    render_table,
    render_dict_table,
    render_panel,
    render_issues,
)


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_default_success(self):
        """Default ToolResult is a success."""
        result = ToolResult()
        assert result.ok is True
        assert result.error == ''

    def test_to_dict_success(self):
        """to_dict includes ok and data."""
        result = ToolResult(ok=True, data={'count': 5})
        d = result.to_dict()
        assert d['ok'] is True
        assert d['count'] == 5
        assert 'error' not in d

    def test_to_dict_failure(self):
        """to_dict includes error on failure."""
        result = ToolResult(ok=False, error='Something failed')
        d = result.to_dict()
        assert d['ok'] is False
        assert d['error'] == 'Something failed'

    def test_success_classmethod(self):
        """ToolResult.success creates success result."""
        result = ToolResult.success(pretty='Done!', count=10)
        d = result.to_dict()
        assert d['ok'] is True
        assert d['count'] == 10
        assert d['pretty'] == 'Done!'

    def test_failure_classmethod(self):
        """ToolResult.failure creates failure result."""
        result = ToolResult.failure('Error message')
        d = result.to_dict()
        assert d['ok'] is False
        assert d['error'] == 'Error message'


class TestResultHelpers:
    """Tests for ok_result and err_result helpers."""

    def test_ok_result(self):
        """ok_result creates success dict."""
        result = ok_result(count=5, items=['a', 'b'])
        assert result['ok'] is True
        assert result['count'] == 5
        assert result['items'] == ['a', 'b']

    def test_err_result(self):
        """err_result creates failure dict."""
        result = err_result('Not found', code=404)
        assert result['ok'] is False
        assert result['error'] == 'Not found'
        assert result['code'] == 404


class TestTryResolve:
    """Tests for try_resolve function."""

    def test_success(self):
        """try_resolve returns success on valid resolution."""
        def mock_resolve(s):
            return f'/path/to/{s}'

        ok, path, error = try_resolve('myproject', mock_resolve)
        assert ok is True
        assert path == '/path/to/myproject'
        assert error == ''

    def test_failure(self):
        """try_resolve returns failure on exception."""
        def failing_resolve(s):
            raise ValueError('Not a project')

        ok, path, error = try_resolve('bad', failing_resolve)
        assert ok is False
        assert path is None
        assert 'Not a project' in error


class TestWithProjectDecorator:
    """Tests for with_project decorator."""

    def test_decorator_resolves_project(self):
        """Decorator passes resolved path to function."""
        def mock_resolve(s):
            return f'/resolved/{s}'

        @with_project(mock_resolve)
        def my_tool(project, extra_arg):
            return {'ok': True, 'path': project, 'arg': extra_arg}

        result = my_tool('myproj', extra_arg='test')
        assert result['ok'] is True
        assert result['path'] == '/resolved/myproj'
        assert result['arg'] == 'test'

    def test_decorator_handles_error(self):
        """Decorator returns error dict on resolution failure."""
        def failing_resolve(s):
            raise ValueError('Invalid project')

        @with_project(failing_resolve)
        def my_tool(project):
            return {'ok': True}

        result = my_tool('bad')
        assert result['ok'] is False
        assert 'Invalid project' in result['error']


class TestConsoleHelpers:
    """Tests for console output helpers."""

    def test_make_console(self):
        """make_console creates a Rich Console."""
        c = make_console()
        assert c is not None

    def test_get_output(self):
        """get_output extracts recorded text."""
        c = make_console()
        c.print("Hello, world!")
        output = get_output(c)
        assert "Hello" in output


class TestRenderFunctions:
    """Tests for render_* functions."""

    def test_render_table(self):
        """render_table creates formatted table text."""
        rows = [['Alice', '30'], ['Bob', '25']]
        output = render_table('People', ['Name', 'Age'], rows)
        assert 'People' in output
        assert 'Alice' in output
        assert 'Bob' in output

    def test_render_table_max_rows(self):
        """render_table respects max_rows."""
        rows = [[f'item{i}', str(i)] for i in range(100)]
        output = render_table('Items', ['Name', 'Value'], rows, max_rows=10)
        # Should only include first 10 rows
        assert 'item0' in output
        assert 'item9' in output

    def test_render_dict_table(self):
        """render_dict_table creates key-value table."""
        data = {'name': 'test', 'count': 42}
        output = render_dict_table('Info', data)
        assert 'name' in output
        assert 'test' in output
        assert '42' in output

    def test_render_panel(self):
        """render_panel creates titled panel."""
        output = render_panel('Status', 'All systems go!')
        assert 'Status' in output
        assert 'All systems go' in output


class TestIssue:
    """Tests for Issue dataclass."""

    def test_issue_creation(self):
        """Issue can be created with required fields."""
        issue = Issue(rule='no-print', message='Avoid print statements')
        assert issue.rule == 'no-print'
        assert issue.message == 'Avoid print statements'

    def test_issue_to_dict_minimal(self):
        """to_dict includes required fields only."""
        issue = Issue(rule='test', message='Test message')
        d = issue.to_dict()
        assert d['rule'] == 'test'
        assert d['message'] == 'Test message'
        assert 'file' not in d
        assert 'cell' not in d

    def test_issue_to_dict_full(self):
        """to_dict includes all specified fields."""
        issue = Issue(
            rule='no-print',
            message='Avoid print',
            notebook='test.ipynb',
            cell=5,
            line=10,
            suggestion='Use logger instead'
        )
        d = issue.to_dict()
        assert d['notebook'] == 'test.ipynb'
        assert d['cell'] == 5
        assert d['line'] == 10
        assert d['suggestion'] == 'Use logger instead'


class TestRenderIssues:
    """Tests for render_issues function."""

    def test_render_issues_basic(self):
        """render_issues creates formatted output."""
        issues = [
            Issue(rule='no-print', message='Avoid print', notebook='test.ipynb', cell=5),
            Issue(rule='type-hint', message='Add type hints', file='utils.py'),
        ]
        output = render_issues(issues)
        assert 'no-print' in output
        assert 'type-hint' in output
        assert 'test.ipynb' in output
