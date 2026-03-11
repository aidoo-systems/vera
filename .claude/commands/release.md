Tag a new semver release and generate changelog.

1. Check `git status` is clean — abort if there are uncommitted changes
2. Run `git-cliff --unreleased` to preview what will be in this release
3. If `$ARGUMENTS` is provided, use it as the version (e.g., `v1.1.0`). Otherwise, ask the user for the version number.
4. Run `git-cliff --tag <version> -o CHANGELOG.md` to update the changelog
5. Stage and commit: `git add CHANGELOG.md && git commit -m "chore: release <version>"`
6. Create annotated tag: `git tag -a <version> -m "Release <version>"`
7. Remind the user to push with `git push origin master --tags`
