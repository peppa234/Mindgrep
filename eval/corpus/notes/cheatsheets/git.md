# Git cheatsheet

## Find the commit that broke something

    git bisect start
    git bisect bad HEAD
    git bisect good v1.4.0
    # test, then mark each step:
    git bisect good   # or: git bisect bad
    git bisect reset

`git bisect run pytest tests/test_x.py` automates it with any command that exits non-zero on failure.

## Rewrite the last few commits

`git rebase -i HEAD~3`, then `fixup` to squash without keeping the message, `reword` to edit it.
Never rebase commits that are already pushed to a shared branch.

## Undo

- Unstage a file: `git restore --staged path`
- Throw away local changes to a file: `git restore path`
- Recover a commit after a bad reset: `git reflog`, then `git reset --hard <sha>`
