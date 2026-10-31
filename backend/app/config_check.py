"""Refuse to run in production with development settings (Phase 17, docs/security/tls.md).

With APP_ENV=production the API does not start while any of these is left at its dev value: every
default in compose.yaml is fine on one machine and a hole anywhere else."""

DEV_PASSWORDS = {
    "ADMIN_PASSWORD": "admin-dev-password",
    "MYSQL_PASSWORD": "changeme",
    "API_MQTT_PASSWORD": "api-dev-password",
}


def production_problems(env) -> list[str]:
    """What stops `env` (a mapping like os.environ) from being a production configuration."""
    problems = []
    secret = env.get("JWT_SECRET", "")
    if len(secret.encode()) < 32:
        problems.append("JWT_SECRET must be set to at least 32 random bytes (and kept the same across restarts)")
    for name, dev_value in DEV_PASSWORDS.items():
        if env.get(name, dev_value) == dev_value:
            problems.append(f"{name} is still the development default")
    if not env.get("MQTT_TLS_CA"):
        problems.append("MQTT_TLS_CA is not set: the API would talk to the broker unencrypted")
    if not env.get("MYSQL_SSL_CA"):
        problems.append("MYSQL_SSL_CA is not set: the API would talk to MySQL unencrypted")
    return problems
