# auth-service

Small FastAPI service that issues and verifies JWT access tokens for the student portal.

- `POST /auth/login` exchanges email + password for an access token and a refresh token
- `POST /auth/refresh` rotates the refresh token
- Passwords are hashed with Argon2id
- Login attempts are rate limited per IP with a sliding window in Redis

Run locally with `uvicorn app.main:app --reload`.
