"""TLS certificates for the stack (Phase 17, docs/security/tls.md): a private certificate authority
and one server certificate that nginx, Mosquitto and MySQL present. Run by the `certs` Compose service
before anything else starts:

    python docker/tls/make_certs.py /certs --hosts localhost,127.0.0.1,mqtt,dashboard,mysql

Existing files are kept, so a browser that trusts ca.crt keeps trusting it. The server certificate is
re-issued only when it is ours (signed by ca.crt) and is missing a host name or expires within 30 days.
A certificate from a real CA put in place of server.crt / server.key is never touched.
"""

import argparse
import datetime
import ipaddress
import os
import sys
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CA_DAYS = 3650
# Browsers reject server certificates valid for more than 398 days.
SERVER_DAYS = 397
RENEW_DAYS = 30
DEFAULT_HOSTS = "localhost,127.0.0.1,mqtt,dashboard,mysql"


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _write(path: Path, data: bytes, mode: int):
    path.write_bytes(data)
    os.chmod(path, mode)


def _key_pem(key) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def _san(hosts: list[str]) -> x509.SubjectAlternativeName:
    names = []
    for host in hosts:
        try:
            names.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            names.append(x509.DNSName(host))
    return x509.SubjectAlternativeName(names)


def _covered_hosts(cert: x509.Certificate) -> set[str]:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return set()
    return set(san.get_values_for_type(x509.DNSName)) | {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}


def make_ca(out: Path):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SmartIoT Dev CA")])
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(_now() - datetime.timedelta(minutes=5))
            .not_valid_after(_now() + datetime.timedelta(days=CA_DAYS))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=True,
                                         crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256()))
    _write(out / "ca.key", _key_pem(key), 0o600)
    _write(out / "ca.crt", cert.public_bytes(serialization.Encoding.PEM), 0o644)


def make_server(out: Path, hosts: list[str]):
    ca_cert = x509.load_pem_x509_certificate((out / "ca.crt").read_bytes())
    ca_key = serialization.load_pem_private_key((out / "ca.key").read_bytes(), password=None)
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hosts[0])]))
            .issuer_name(ca_cert.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(_now() - datetime.timedelta(minutes=5))
            .not_valid_after(_now() + datetime.timedelta(days=SERVER_DAYS))
            .add_extension(_san(hosts), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                         crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    _write(out / "server.key", _key_pem(key), 0o600)
    _write(out / "server.crt", cert.public_bytes(serialization.Encoding.PEM), 0o644)


def server_needs_renewal(out: Path, hosts: list[str]) -> str | None:
    """Why server.crt must be (re)issued, or None to keep it."""
    if not (out / "server.crt").exists() or not (out / "server.key").exists():
        return "no server certificate"
    cert = x509.load_pem_x509_certificate((out / "server.crt").read_bytes())
    ca_cert = x509.load_pem_x509_certificate((out / "ca.crt").read_bytes())
    try:
        # By signature, not by name: every CA this script makes is called "SmartIoT Dev CA".
        cert.verify_directly_issued_by(ca_cert)
    except (ValueError, TypeError, InvalidSignature):
        return None  # someone else's certificate (e.g. a real CA): theirs to renew
    missing = set(hosts) - _covered_hosts(cert)
    if missing:
        return f"not valid for {', '.join(sorted(missing))}"
    if cert.not_valid_after_utc - _now() < datetime.timedelta(days=RENEW_DAYS):
        return "expires within 30 days"
    return None


def ensure(out: Path, hosts: list[str]) -> list[str]:
    """Create whatever is missing or due in `out`. Returns what was done, for the log."""
    out.mkdir(parents=True, exist_ok=True)
    done = []
    if not (out / "ca.crt").exists():
        if (out / "server.crt").exists():
            return []  # bring-your-own certificates without our CA: leave everything alone
        make_ca(out)
        done.append("created CA ca.crt")
    reason = server_needs_renewal(out, hosts)
    if reason:
        if not (out / "ca.key").exists():
            raise SystemExit(f"server certificate needs re-issuing ({reason}) but ca.key is missing")
        make_server(out, hosts)
        done.append(f"issued server.crt for {', '.join(hosts)} ({reason})")
    return done


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--hosts", default=os.getenv("TLS_HOSTNAMES") or DEFAULT_HOSTS,
                        help=f"comma-separated DNS names and IPs (default {DEFAULT_HOSTS})")
    args = parser.parse_args(argv)
    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    done = ensure(args.out, hosts)
    print("\n".join(f"certs: {line}" for line in done) or "certs: up to date, nothing to do")
    return 0


if __name__ == "__main__":
    sys.exit(main())
