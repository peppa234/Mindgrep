---
title: Code review bot
created: 2023-11-02
tags: [idea, llm, devtools]
---

# Code review bot

A GitHub app that comments on pull requests, but only about things a linter cannot see:
missing tests for a changed branch, an error swallowed in a new except block, a migration
without a downgrade.

## Constraints I set myself

- At most three comments per PR, or people mute it.
- Every comment must cite the exact line and say why, never "consider refactoring".
- Run on the diff plus the call sites of changed functions, not the whole repository.

## Open questions

How to evaluate it? Maybe replay merged PRs from open-source repos and check whether the
bot flags lines that were later fixed in follow-up commits. #evaluation
