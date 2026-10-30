# Authentication and Roles

Every endpoint except `GET /health` needs a bearer token. You get one by signing in.

```bash
curl -s -X POST http://localhost:8000/auth/login -H 'content-type: application/json' \
     -d '{"username":"admin","password":"admin-dev-password"}'
# {"access_token":"eyJ...","token_type":"bearer","expires_in":3600,"user":{"username":"admin","role":"ADMIN",...}}

curl -s http://localhost:8000/sensors -H "Authorization: Bearer eyJ..."
```

In Swagger UI (`/docs`), use **Authorize** and paste the token.

## Roles

Each role can do everything the roles before it can.

| Role | Can |
|---|---|
| `VIEWER` | Read sensors, telemetry and alerts (`GET` endpoints), and `GET /auth/me` |
| `OPERATOR` | Also change a sensor's name and location (`PATCH /sensors/{id}`), send commands, and start firmware updates |
| `ADMIN` | Also manage users (`/users`) and upload firmware |

The role is read from the database on **every request**, not from the token. Deleting a user or changing their role therefore takes effect immediately, and a token can't grant more than its user has. A token that claims `ADMIN` for a `VIEWER` still only gets `VIEWER` rights.

## Endpoints

| Method | Path | Role | Success | Errors |
|---|---|---|---|---|
| POST | `/auth/login` | none | `200` token + user | `401` wrong username or password (one message for both), `422` malformed body |
| GET | `/auth/me` | any | `200` the signed-in user | `401` |
| GET | `/users` | ADMIN | `200` users sorted by name (never the hash) | `401`, `403` |
| POST | `/users` | ADMIN | `201` the new user | `409` name taken, `422` invalid, `401`, `403` |
| DELETE | `/users/{username}` | ADMIN | `204` | `400` deleting yourself, `404`, `401`, `403` |
| PATCH | `/sensors/{sensor_id}` | OPERATOR | `200` the updated sensor | `404`, `422`, `401`, `403` |

`POST /users` body: `{"username": "olga", "password": "at-least-8", "role": "OPERATOR"}`. Usernames are 3–50 characters from `A-Z a-z 0-9 _ . -`, and comparison is case-insensitive (MySQL collation). Passwords are 8–128 characters. `role` defaults to `VIEWER`.

`PATCH /sensors/{id}` body: `{"name": "...", "location": "..."}`. Only the fields you send change. Values are trimmed, an empty value clears the field, the maximum is 100 characters, and control characters are rejected. At least one field is required. Unknown fields such as `status` are rejected with `422`, so the endpoint can't be used to fake sensor state.

| Status | Body | Meaning |
|---|---|---|
| `401` | `{"detail": "Not authenticated"}` | No `Authorization: Bearer` header |
| `401` | `{"detail": "Token expired"}` | Sign in again (the dashboard does this automatically) |
| `401` | `{"detail": "Invalid token"}` | Malformed or tampered token, signed with another secret, or the user was deleted |
| `403` | `{"detail": "Requires role OPERATOR or higher"}` | Signed in, but not allowed |

Every `401` carries `WWW-Authenticate: Bearer`.

## How it works

- **Passwords:** salted scrypt (n=2¹⁴, r=8, p=1, about 50 ms) from the Python standard library, stored as `scrypt$n$r$p$salt$hash` so the cost can be raised later. Plain passwords are never stored or logged. A `422` never echoes a rejected password back.
- **Login timing:** an unknown username still runs one hash check against a dummy hash, so it takes as long as a wrong password and response times don't reveal which usernames exist.
- **Tokens:** JWT signed with HS256. Claims are `sub` (username), `role` (informational), `iat` and `exp`. The algorithm is pinned on decode, so `alg: none` and algorithm-swap tokens are rejected, and `exp` is required.
- **Lifetime:** `TOKEN_MINUTES`, default 60. There is no refresh token: the dashboard returns to the login form with "Token expired".
- **Secret:** `JWT_SECRET`. If it isn't set, the API uses a random secret per start (safe, but everyone signs in again after a restart) and logs a warning. It also warns about a secret shorter than 32 bytes.
- **First admin:** when the `users` table is empty, the API creates `ADMIN_USERNAME` (default `admin`) with `ADMIN_PASSWORD` on startup. After that, changing `ADMIN_PASSWORD` changes nothing. Manage accounts through `/users`. Compose's dev default password is `admin-dev-password`. Set your own in `.env`.
- **Dashboard:** keeps the login response in `sessionStorage` (gone when the tab closes) and sends the token with every request. On any `401` it signs out and shows the reason. Edit controls are only shown to OPERATOR and above, but the API enforces every permission itself.

Rate limiting of login attempts is added in the security part (15g).
