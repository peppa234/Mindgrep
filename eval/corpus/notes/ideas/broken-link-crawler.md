---
title: Broken link crawler
created: 2023-05-14
tags: [idea, tooling]
---

# Broken link crawler

A command-line crawler that walks the course wiki, follows every link up to a maximum depth,
and reports broken links with their HTTP status and the page they were found on. It has to
respect robots.txt and fetch pages concurrently with a small pool of workers.

## Why

Half the links to lecture slides return 404 after every semester, and nobody notices until
the week before the exam.
