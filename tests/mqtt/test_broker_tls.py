"""The broker's TLS listener (Phase 17, docs/security/tls.md): what devices and services use. Each test
connects the way a client would, and checks that only a correctly verified TLS connection gets through."""

import os
import queue
import socket
import ssl
import uuid

import paho.mqtt.client as mqtt
import pytest

from helpers import MQTT_HOST, mqtt_client

TLS_PORT = int(os.getenv("MQTT_TLS_PORT", "8883"))
CA_FILE = os.getenv("TLS_CA_FILE", "")

pytestmark = [pytest.mark.usefixtures("broker_available"),
              pytest.mark.skipif(not CA_FILE, reason="TLS_CA_FILE not set (compose.test.yaml sets it)")]


def context(cafile=CA_FILE, **settings):
    ctx = ssl.create_default_context(cafile=cafile or None)
    for name, value in settings.items():
        setattr(ctx, name, value)
    return ctx


def connect_tls(ctx, host=MQTT_HOST, username="qa", password=None):
    """CONNACK reason code of a TLS connection, or the exception the TLS handshake raised."""
    client = mqtt_client(username=username, password=password)
    client.tls_set_context(ctx)
    result = queue.Queue()
    client.on_connect = lambda c, u, f, rc, p: result.put(rc)
    try:
        client.connect(host, TLS_PORT)
    except (ssl.SSLError, OSError) as exc:
        return exc
    client.loop_start()
    try:
        return result.get(timeout=5)
    finally:
        client.loop_stop()
        client.disconnect()


def test_publish_and_receive_over_tls():
    topic = f"iot/sensors/TEST-TLS-{uuid.uuid4().hex[:6]}/telemetry"
    received = queue.Queue()
    clients = []
    for role in ("sub", "pub"):
        client = mqtt_client()
        client.tls_set_context(context())
        connected = queue.Queue()
        client.on_connect = lambda c, u, f, rc, p, q=connected: q.put(rc)
        client.connect(MQTT_HOST, TLS_PORT)
        client.loop_start()
        assert connected.get(timeout=5) == 0
        clients.append(client)
    sub, pub = clients
    sub.on_message = lambda c, u, msg: received.put(msg.payload)
    subscribed = queue.Queue()
    sub.on_subscribe = lambda c, u, mid, rc, p: subscribed.put(rc)
    sub.subscribe(topic, qos=1)
    subscribed.get(timeout=5)
    pub.publish(topic, b'{"over": "tls"}', qos=1).wait_for_publish(5)
    try:
        assert received.get(timeout=5) == b'{"over": "tls"}'
    finally:
        for client in clients:
            client.loop_stop()
            client.disconnect()


def test_tls_1_2_or_newer_with_a_certificate_for_the_broker_name():
    with socket.create_connection((MQTT_HOST, TLS_PORT), timeout=5) as raw:
        with context().wrap_socket(raw, server_hostname=MQTT_HOST) as tls:
            assert tls.version() in ("TLSv1.2", "TLSv1.3")
            assert ("DNS", MQTT_HOST) in tls.getpeercert()["subjectAltName"]


@pytest.mark.filterwarnings("ignore:ssl.TLSVersion.TLSv1_1 is deprecated:DeprecationWarning")
def test_tls_1_1_is_refused_by_the_broker():
    # Python's OpenSSL won't even offer TLS 1.1 by default (NO_CIPHERS_AVAILABLE), which would make this
    # pass without asking the broker. SECLEVEL=0 lets the client offer it, so the refusal is the broker's.
    ctx = context()
    ctx.minimum_version = ctx.maximum_version = ssl.TLSVersion.TLSv1_1
    ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
    error = connect_tls(ctx)
    assert isinstance(error, ssl.SSLError) and error.reason == "TLSV1_ALERT_PROTOCOL_VERSION"


def test_a_client_without_our_ca_refuses_the_broker():
    # The OS trust store doesn't know our CA: exactly what a client sees from a man in the middle.
    error = connect_tls(context(cafile=""))
    assert isinstance(error, ssl.SSLCertVerificationError)


def test_the_host_name_is_checked():
    # Same broker, same certificate, but reached by IP address, which the certificate doesn't list.
    ip = socket.gethostbyname(MQTT_HOST)
    error = connect_tls(context(), host=ip)
    assert isinstance(error, ssl.SSLCertVerificationError) and "IP address mismatch" in str(error)


def test_tls_does_not_replace_the_password():
    reason = connect_tls(context(), password="wrong")
    assert isinstance(reason, mqtt.ReasonCode) and reason.is_failure


def test_plain_mqtt_on_the_tls_port_gets_nowhere():
    client = mqtt_client()
    connected = queue.Queue()
    client.on_connect = lambda c, u, f, rc, p: connected.put(rc)
    client.connect(MQTT_HOST, TLS_PORT)
    client.loop_start()
    try:
        with pytest.raises(queue.Empty):
            connected.get(timeout=3)
    finally:
        client.loop_stop()
        client.disconnect()
