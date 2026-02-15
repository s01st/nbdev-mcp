# Git Best Practices for nbdev Projects

## Branch Strategy

```
main          <- stable releases only (protected)
  └── dev     <- active development base (default PR target)
        ├── feat/feature-name
        ├── fix/bug-description
        └── refactor/cleanup-name
```

**Branches:**
- `main` - Production-ready, stable releases only. Protected branch.
- `dev` - Active development. All feature branches merge here first.
- `feat/*` - New features, branch from `dev`
- `fix/*` - Bug fixes, branch from `dev`
- `docs/*` - Documentation updates
- `refactor/*` - Code improvements without behavior change

**Workflow:**
1. Create feature branch from `dev`: `git checkout -b feat/my-feature dev`
2. Work and commit on feature branch
3. PR feature branch → `dev`
4. After testing on `dev`, PR `dev` → `main` for releases

## Branch Naming

```
<type>/<short-description>
```

**Examples:**
```
feat/dependency-graph
fix/import-detection
docs/api-reference
refactor/utils-cleanup
```

## Commit Messages

Follow conventional commit format:
```
<type>(<scope>): <subject>

[optional body]

[optional footer]
```

**Types:** `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `style`

**Scope:** module or notebook name (e.g., `utils`, `tools`, `00_config`)

**Examples:**
```
feat(analysis): add dependency graph visualization
fix(editing): correct cell index bounds checking
docs(index): update installation instructions
refactor(nb): extract common parsing logic
```

## Commit Hygiene

- **Atomic commits**: One logical change per commit
- **Run `{nbdev_prepare_cmd}` before committing**: Ensures exports are clean
- **Never commit generated `.py` files alone**: Always commit notebook source
- **Verify clean notebooks**: Run `nbdev_clean` if needed

## NO Agent Attribution

Do NOT include AI/agent signatures in commits:
```
# BAD - Remove these:
Source library: ...
Generated with [Claude Code]
Co-Authored-By: Claude ...
Co-Authored-By: ... <noreply@anthropic.com>
```

Keep commits clean and human-readable. The git history should reflect the project's evolution, not the tools used to create it.

## Pre-Commit Checklist

1. `{nbdev_export_cmd}` - regenerate Python modules
2. `{nbdev_test_cmd}` - run notebook tests
3. `nbdev_clean` - clean notebook metadata
4. Review `git diff` - verify only intended changes
5. Remove any AI attribution from commit message

## Pull Requests

- **Target branch**: `dev` (not `main` unless releasing)
- **Title**: Same format as commit subject
- **Body**: Describe what and why, not how
- Link related issues
- Include test evidence if applicable
- Keep PRs focused - one feature or fix per PR

## Tagging & Releases

Use semantic versioning: `vMAJOR.MINOR.PATCH`

- **MAJOR**: Breaking API changes
- **MINOR**: New features, backward compatible
- **PATCH**: Bug fixes, backward compatible

**Tagging workflow:**
```bash
# After merging dev → main
git checkout main
git pull origin main
git tag -a v1.2.0 -m "Release v1.2.0: brief description"
git push origin v1.2.0
```

**Pre-release tags:**
```
v1.2.0-alpha.1   # Early testing
v1.2.0-beta.1    # Feature complete, testing
v1.2.0-rc.1      # Release candidate
```

**Tag on main only** - never tag dev or feature branches.

**Update version in code:**
- `{nbdev_settings_file}`: set project/package version there (format depends on the file type)
- Commit version bump before tagging

## .gitignore Essentials

```
# Generated files
{lib}/
*.pyc
__pycache__/

# Notebook checkpoints
.ipynb_checkpoints/

# Build artifacts
dist/
*.egg-info/
_docs/
```

## Sensitive Data

Never commit:
- API keys or tokens
- Credentials or passwords
- Personal data or PII
- Large binary files (use Git LFS or exclude)
