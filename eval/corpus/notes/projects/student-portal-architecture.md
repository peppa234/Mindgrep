---
title: Student Portal architecture
created: 2023-09-20
tags: [project, architecture]
---

# Student Portal architecture

## Original design (v1, September 2023)

A single Django monolith with server-rendered templates, one PostgreSQL database, and Celery
with RabbitMQ for sending grade notification emails. Deployed on one VM with Nginx and
Gunicorn. Authentication through Django sessions.

It worked, but every page load hit the database for the timetable, and exam week took it down.

## Current design (v2, 2024)

- Next.js frontend, FastAPI backend split out of the monolith.
- Auth moved to a separate [[auth-service]] issuing JWTs.
- Redis caches the timetable per group with a one-hour TTL.
- Celery replaced by ARQ, RabbitMQ removed.

## Lessons

Cache first, split services second. The split did not fix exam week; the timetable cache did.
