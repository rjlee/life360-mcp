# Release Workflow

This project uses **semantic-release** for automated releases.

## Setup

1. **Install semantic-release globally:**
   ```bash
   npm install -g semantic-release
   ```

2. **Create a GitHub Personal Access Token** with `repo` scope.

3. **Set the token as an environment variable:**
   ```bash
   export GH_TOKEN=your_personal_access_token
   ```

4. **Run a release (dry-run first):**
   ```bash
   npx semantic-release --dry-run
   ```

5. **Run the actual release:**
   ```bash
   npx semantic-release
   ```

## How It Works

- On every push to `main`, semantic-release analyzes commits since the last release
- Based on commit messages (following Conventional Commits), it determines the next version:
  - `feat:` → minor version bump
  - `fix:` → patch version bump
  - `feat!:` or `fix!:` → major version bump
- Creates a GitHub release with changelog
- Updates version in `pyproject.toml`

## Commit Message Format

Use Conventional Commits:
```
feat: add new endpoint
fix: resolve authentication issue
docs: update README
chore: update dependencies
```

## CI/CD (GitHub Actions)

Add `.github/workflows/release.yml`:

```yaml
name: Release
on:
  push:
    branches: [main]

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm install -g semantic-release
      - env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
        run: semantic-release
```

Note: You'll need to add `GH_TOKEN` as a repository secret in GitHub Settings → Secrets → Actions.