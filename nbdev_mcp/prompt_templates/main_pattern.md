# nbdev __main__ and Console Scripts

## Safe __main__ patterns
1) Same notebook, separate cell:
```python
#| export
#| eval: false
if __name__ == "__main__":
    import sys
    sys.exit(main())
```

2) Dedicated _main__ notebook:
- Notebook name: `01__main__.ipynb`
- Cell: `#| default_exp pkg.__main__`
- Export a tiny wrapper that imports and calls your real `main`.

3) Export directly to __main__:
```python
#| export __main__
#| eval: false
if __name__ == "__main__":
    import sys
    sys.exit(main())
```

## Console scripts
- Add to `{nbdev_settings_file}`: `console_scripts = mycli=mypkg:main` (or TOML equivalent list format).
- After `{nbdev_export_cmd}`, setuptools exposes `mycli` as an entry point.
