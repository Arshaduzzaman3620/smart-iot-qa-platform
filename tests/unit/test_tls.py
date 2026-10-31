"""TLS (Phase 17, docs/security/tls.md): the certificate generator, HTTPS firmware downloads, the MQTT
clients' TLS settings and the API's production check. No services needed: a local HTTPS server stands
in for the API."""

import contextlib
import datetime
import http.server
import importlib.util
import os
import ssl
import threading

import pytest
from cryptography import x509

from backend.app.config_check import production_problems
from fota.fota_client import FotaError, download
from helpers import ROOT

_spec = importlib.util.spec_from_file_location("make_certs", ROOT / "docker" / "tls" / "make_certs.py")
make_certs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_certs)


def load(path):
    return x509.load_pem_x509_certificate(path.read_bytes())


def module(name, path):
    """Receiver and simulator both have an `mqtt` package, so each wrapper is loaded from its file."""
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def certs(tmp_path):
    make_certs.ensure(tmp_path, ["localhost", "127.0.0.1"])
    return tmp_path


# ---- certificate generator -------------------------------------------------------------------------

def test_server_certificate_is_signed_by_the_ca_for_every_host(certs):
    ca, server = load(certs / "ca.crt"), load(certs / "server.crt")
    server.verify_directly_issued_by(ca)
    assert make_certs._covered_hosts(server) == {"localhost", "127.0.0.1"}
    assert server.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value == \
        x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH])
    assert not server.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    # Browsers reject longer server certificates.
    assert server.not_valid_after_utc - server.not_valid_before_utc <= datetime.timedelta(days=398)


def test_private_keys_are_readable_by_the_owner_only(certs):
    for name in ("ca.key", "server.key"):
        assert os.stat(certs / name).st_mode & 0o777 == 0o600
    assert os.stat(certs / "ca.crt").st_mode & 0o777 == 0o644


def test_second_run_keeps_everything(certs):
    before = {n: (certs / n).read_bytes() for n in ("ca.crt", "ca.key", "server.crt", "server.key")}
    assert make_certs.ensure(certs, ["localhost", "127.0.0.1"]) == []
    assert before == {n: (certs / n).read_bytes() for n in before}


def test_new_host_reissues_the_server_certificate_but_keeps_the_ca(certs):
    ca_before = (certs / "ca.crt").read_bytes()
    done = make_certs.ensure(certs, ["localhost", "127.0.0.1", "iot.example.com"])
    assert done == ["issued server.crt for localhost, 127.0.0.1, iot.example.com (not valid for iot.example.com)"]
    assert (certs / "ca.crt").read_bytes() == ca_before  # browsers that trust it keep trusting it
    assert "iot.example.com" in make_certs._covered_hosts(load(certs / "server.crt"))


def test_a_certificate_from_another_ca_is_never_replaced(certs, tmp_path_factory):
    other = tmp_path_factory.mktemp("other")
    make_certs.ensure(other, ["iot.example.com"])
    for name in ("server.crt", "server.key"):  # a "real" certificate put in place
        (certs / name).write_bytes((other / name).read_bytes())
    assert make_certs.ensure(certs, ["localhost", "mqtt"]) == []
    assert (certs / "server.crt").read_bytes() == (other / "server.crt").read_bytes()


def test_bring_your_own_certificates_without_a_ca_are_left_alone(tmp_path):
    (tmp_path / "server.crt").write_text("real certificate")
    (tmp_path / "server.key").write_text("real key")
    assert make_certs.ensure(tmp_path, ["localhost"]) == []
    assert not (tmp_path / "ca.crt").exists()


# ---- firmware download over HTTPS ------------------------------------------------------------------

@contextlib.contextmanager
def https_server(cert_dir):
    """A local HTTPS server presenting cert_dir's server certificate, serving 'image' for any path."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "5")
            self.end_headers()
            self.wfile.write(b"image")

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_dir / "server.crt", cert_dir / "server.key")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"https://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def test_download_over_https_checks_the_certificate_against_our_ca(certs):
    with https_server(certs) as url:
        assert download(url, "/firmware/1/download", ca_file=str(certs / "ca.crt")) == b"image"


def test_download_refuses_a_certificate_it_cannot_verify(certs):
    # Without our CA the OS trust store is used, which doesn't know it: like a man in the middle.
    with https_server(certs) as url, pytest.raises(FotaError, match="CERTIFICATE_VERIFY_FAILED"):
        download(url, "/firmware/1/download")


def test_download_refuses_a_certificate_for_another_host(tmp_path):
    make_certs.ensure(tmp_path, ["localhost"])  # trusted CA, but not valid for 127.0.0.1
    with https_server(tmp_path) as url, pytest.raises(FotaError, match="CERTIFICATE_VERIFY_FAILED"):
        download(url, "/firmware/1/download", ca_file=str(tmp_path / "ca.crt"))


# ---- MQTT clients ----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["receiver/mqtt/mqtt_client.py", "sensor-simulator/mqtt/mqtt_client.py",
                                  "backend/app/mqtt_publisher.py"])
def test_mqtt_tls_context_verifies_certificate_and_host_name(path, certs):
    context = module(path.replace("/", "_"), path).tls_context(str(certs / "ca.crt"))
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert context.minimum_version == ssl.TLSVersion.TLSv1_2


def test_mqtt_clients_use_tls_only_when_given_a_ca(certs):
    receiver = module("receiver_mqtt", "receiver/mqtt/mqtt_client.py")
    simulator = module("simulator_mqtt", "sensor-simulator/mqtt/mqtt_client.py")
    publisher = module("api_mqtt", "backend/app/mqtt_publisher.py")
    ca = str(certs / "ca.crt")
    assert receiver.MQTTSubscriber("mqtt", 8883, tls_ca=ca)._client._ssl_context is not None
    assert simulator.MQTTClient("mqtt", 8883, "S-1", tls_ca=ca)._client._ssl_context is not None
    assert publisher.CommandPublisher("mqtt", 8883, tls_ca=ca)._client._ssl_context is not None
    assert receiver.MQTTSubscriber("mqtt", 1883)._client._ssl_context is None


# ---- production check ------------------------------------------------------------------------------

PRODUCTION = {"JWT_SECRET": "x" * 32, "ADMIN_PASSWORD": "a-real-one", "MYSQL_PASSWORD": "another",
              "API_MQTT_PASSWORD": "third", "MQTT_TLS_CA": "/certs/ca.crt", "MYSQL_SSL_CA": "/certs/ca.crt"}


def test_a_complete_production_configuration_passes():
    assert production_problems(PRODUCTION) == []


@pytest.mark.parametrize("change, problem", [
    ({"JWT_SECRET": ""}, "JWT_SECRET"),
    ({"JWT_SECRET": "short"}, "JWT_SECRET"),
    ({"ADMIN_PASSWORD": "admin-dev-password"}, "ADMIN_PASSWORD"),
    ({"MYSQL_PASSWORD": "changeme"}, "MYSQL_PASSWORD"),
    ({"API_MQTT_PASSWORD": "api-dev-password"}, "API_MQTT_PASSWORD"),
    ({"MQTT_TLS_CA": ""}, "MQTT_TLS_CA"),
    ({"MYSQL_SSL_CA": ""}, "MYSQL_SSL_CA"),
])
def test_each_development_setting_is_reported(change, problem):
    (found,) = production_problems({**PRODUCTION, **change})
    assert found.startswith(problem)


def test_unset_passwords_count_as_the_development_defaults():
    env = {k: v for k, v in PRODUCTION.items() if k != "ADMIN_PASSWORD"}
    assert production_problems(env) == ["ADMIN_PASSWORD is still the development default"]


def test_api_refuses_to_start_in_production_with_dev_settings(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.app.main import app

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="APP_ENV=production"):
        with TestClient(app):
            pass
