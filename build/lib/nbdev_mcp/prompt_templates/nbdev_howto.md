# nbdev quick how-to for {lib}

- **Notebooks live in** `{nbs_path}/`. The `index.ipynb` becomes **README.md** and the docs home page.
- 
- **Declare module** at top of notebook:
    ```python
    #| default_exp your_module_name
    ```
- **Exports**: mark cells with `#| export` (to include in library) or `#| exporti` (to include as internal).

- **Hide or control output**: `#| hide` to hide a cell, `#| echo: false` to hide code, `#| output: false` to hide outputs.

- **Collapse sections**: Use `#| code-fold: true` to make a long code cell folded by default.

- **Skip execution**: `#| eval: false` to prevent a cell from running during tests.

- **Doclinks**: Use backticks to reference symbols (e.g., `` `numpy.array` ``) which auto-link in docs.

- **Quarto features**: You can use callouts, columns, figures, mermaid diagrams, math blocks, etc., in Markdown.

- **Frontmatter**: Add YAML between `---` at the top or use the first cell (with `# Title` and possibly a description and key metadata).

- **Cell granularity**: keep __one__ function/class per code cell; split markdown by headings (use the `split_markdown_cells` tool when converting large markdown blobs).

- **Live reload**: Use autoreload in notebooks for iterative development:
    ```python
    %load_ext autoreload
    %autoreload 2
    from nbdev.showdoc import show_doc
    ```
