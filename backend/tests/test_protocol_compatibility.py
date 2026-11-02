"""Share-link compatibility against the 3x-ui/Xray and Hysteria URI formats."""

import base64
import json
import os
import shutil
import subprocess
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import pytest
import yaml

from sboard.models import Node
from sboard.schemas import NodeCreate
from sboard.services.importer import parse_share_link
from sboard.services.subscriptions import _clash_proxy, share_link

UUID = "11111111-1111-1111-1111-111111111111"
KEY = "SYB2tzJR0OfHxHLHsOTR9mQVdq61IgxyhDBDgCS6DBE"
PIN = "12" * 32
PASSWORD = "user:pa%25:ss@/?#中文"
FM = {
    "tcp": [
        {
            "type": "header-custom",
            "settings": {
                side: [
                    [
                        {
                            "delay": 0,
                            "type": "str",
                            "packet": "SSH-2.0-OpenSSH_9.6p1 Ubuntu-3ubuntu13.5\r\n",
                        }
                    ]
                ]
                for side in ("clients", "servers", "errors")
            },
        }
    ],
}


def node_from_link(link):
    payload = NodeCreate.model_validate(parse_share_link(link))
    return Node(
        **payload.model_dump(exclude={"extra", "group_ids", "tag_ids"}), extra_json=payload.extra
    )


def uri(protocol="vless", **params):
    auth = UUID if protocol == "vless" else quote(PASSWORD, safe="")
    return f"{protocol}://{auth}@192.0.2.1:443?{urlencode(params)}#Example"


def vmess_link(**settings):
    data = {
        "v": "2",
        "ps": "VMess",
        "add": "192.0.2.1",
        "port": "443",
        "id": UUID,
        "aid": "0",
        "scy": "auto",
        "net": "ws",
        "tls": "tls",
        **settings,
    }
    return "vmess://" + base64.b64encode(json.dumps(data).encode()).decode()


def test_hysteria_pin_auth_and_port_hopping_roundtrip():
    link = uri(
        "hysteria2",
        sni="example.com",
        insecure=1,
        pinSHA256=PIN,
        obfs="gecko",
        **{
            "obfs-password": "obfs-password",
            "mport": "20000:20010,20443",
            "hopInterval": "10",
            "minPacketSize": 512,
            "maxPacketSize": 1200,
            "alpn": "h3",
            "up": "20 Mbps",
            "down": "100 Mbps",
        },
    )
    node = node_from_link(link)
    assert node.reality is False
    assert node.password == PASSWORD
    proxy = _clash_proxy(node, "HY2")
    assert proxy["fingerprint"] == PIN
    assert proxy["skip-cert-verify"] is True
    assert proxy["ports"] == "20000-20010,20443"
    assert proxy["hop-interval"] == "10"
    assert proxy["obfs-min-packet-size"] == 512
    assert proxy["alpn"] == ["h3"]
    assert proxy["up"] == "20 Mbps"
    restored = node_from_link(share_link(node, "HY2"))
    assert restored.password == node.password
    assert restored.extra_json == node.extra_json
    assert "pinSHA256" in share_link(node, "HY2")
    userpass = node_from_link("hy2://username:password@[2001:db8::1]/?insecure=1")
    assert userpass.password == "username:password"
    assert userpass.port == 443
    assert userpass.address == "2001:db8::1"


@pytest.mark.parametrize(
    "pin", [PIN.upper(), ":".join(["12"] * 32), base64.b64encode(bytes.fromhex(PIN)).decode()]
)
def test_certificate_pin_formats(pin):
    node = node_from_link(uri("hysteria2", pinSHA256=pin))
    assert _clash_proxy(node, "test")["fingerprint"] == PIN


@pytest.mark.parametrize("protocol", ["vless", "trojan"])
def test_tls_and_httpupgrade_roundtrip(protocol):
    node = node_from_link(
        uri(
            protocol,
            security="tls",
            type="httpupgrade",
            host="example.com",
            path="/upgrade",
            sni="example.com",
            alpn="h2,http/1.1",
            fp="firefox",
            allowInsecure="true",
            pcs=base64.b64encode(bytes.fromhex(PIN)).decode(),
        )
    )
    proxy = _clash_proxy(node, protocol)
    assert proxy["network"] == "ws"
    assert proxy["ws-opts"] == {
        "path": "/upgrade",
        "headers": {"Host": "example.com"},
        "v2ray-http-upgrade": True,
    }
    assert proxy["alpn"] == ["h2", "http/1.1"]
    assert proxy["client-fingerprint"] == "firefox"
    assert proxy["fingerprint"] == PIN
    assert proxy["skip-cert-verify"] is True
    restored = node_from_link(share_link(node, protocol))
    assert restored.extra_json == node.extra_json
    assert restored.password == node.password
    assert restored.reality is False


def test_vmess_tls_and_header_roundtrip():
    node = node_from_link(
        vmess_link(
            net="tcp",
            type="http",
            host="example.com",
            path="/test",
            fp="firefox",
            alpn="h2",
            allowInsecure=True,
        )
    )
    proxy = _clash_proxy(node, "VMess")
    assert proxy["network"] == "http"
    assert proxy["http-opts"] == {"path": ["/test"], "headers": {"Host": ["example.com"]}}
    assert proxy["client-fingerprint"] == "firefox"
    assert proxy["skip-cert-verify"] is True
    assert node.reality is False
    assert node_from_link(share_link(node, "VMess")).extra_json == node.extra_json


@pytest.mark.parametrize("encoded", [True, False])
@pytest.mark.parametrize(
    "plugin, expected",
    [
        (
            "obfs-local;obfs=http;obfs-host=example.com",
            {"plugin": "obfs", "plugin-opts": {"mode": "http", "host": "example.com"}},
        ),
        ("v2ray-plugin;mode=websocket;host=example.com;path=/test;tls;foobar", None),
        (
            "v2ray-plugin;mode=websocket;host=example.com;path=/test;tls;mux=false",
            {
                "plugin": "v2ray-plugin",
                "plugin-opts": {
                    "mode": "websocket",
                    "host": "example.com",
                    "path": "/test",
                    "tls": True,
                    "mux": False,
                },
            },
        ),
    ],
)
def test_shadowsocks_plugin_roundtrip(encoded, plugin, expected):
    credentials = "aes-128-gcm:" + PASSWORD
    credentials = (
        base64.urlsafe_b64encode(credentials.encode()).decode()
        if encoded
        else "aes-128-gcm:" + quote(PASSWORD, safe="")
    )
    node = node_from_link(f"ss://{credentials}@192.0.2.1:443?{urlencode({'plugin': plugin})}#SS")
    assert node.password == PASSWORD
    if expected is not None:
        proxy = _clash_proxy(node, "SS")
        for key, value in expected.items():
            assert proxy[key] == value
    else:
        assert _clash_proxy(node, "SS") is None
    assert node_from_link(share_link(node, "SS")).extra_json == node.extra_json
    assert node_from_link(share_link(node, "SS")).password == PASSWORD


def test_tuic_tls_and_auth_roundtrip():
    link = f"tuic://{UUID}:{quote(PASSWORD, safe='')}@192.0.2.1:443?" + urlencode(
        {
            "sni": "example.com",
            "alpn": "h3",
            "allow_insecure": 1,
            "congestion_control": "bbr",
            "udp_relay_mode": "native",
            "disable_sni": 1,
            "reduce_rtt": 1,
        }
    )
    node = node_from_link(link)
    proxy = _clash_proxy(node, "TUIC")
    assert proxy["uuid"] == UUID
    assert proxy["password"] == PASSWORD
    assert proxy["alpn"] == ["h3"]
    assert proxy["disable-sni"] is True
    assert proxy["reduce-rtt"] is True
    assert node_from_link(share_link(node, "TUIC")).extra_json == node.extra_json


def test_finalmask_import_backup_and_clash_warning(client, admin_headers):
    settings = {
        "downloadSettings": {
            "address": "192.0.2.2",
            "port": 443,
            "network": "xhttp",
            "security": "tls",
            "tlsSettings": {"serverName": "cdn.example.com", "alpn": ["h2"]},
            "xhttpSettings": {"host": "cdn.example.com", "path": "/stream", "mode": "auto"},
        }
    }
    link = uri(
        security="reality",
        pbk=KEY,
        sni="example.com",
        type="xhttp",
        path="/stream",
        mode="stream-up",
        extra=json.dumps(settings),
        fm=json.dumps(FM),
    )
    result = client.post(
        "/api/v1/nodes/import", headers=admin_headers, json={"mode": "commit", "links": [link]}
    ).json()
    assert result["created"] == 1
    assert "FinalMask" in result["items"][0]["warning"]
    assert result["items"][0]["node"]["extra"]["finalmask"] == FM
    node = node_from_link(link)
    assert _clash_proxy(node, "masked") is None
    query = parse_qs(urlsplit(share_link(node, "masked")).query)
    assert json.loads(query["fm"][0]) == FM
    assert json.loads(query["extra"][0]) == settings
    backup = client.get("/api/v1/nodes/export", headers=admin_headers).json()
    assert backup["nodes"][0]["extra"]["finalmask"] == FM
    token_response = client.post(
        "/api/v1/subscriptions", headers=admin_headers, json={"name": "masked"}
    ).json()
    sub_id = token_response["subscription"]["id"]
    preview = client.get(f"/api/v1/subscriptions/{sub_id}/preview", headers=admin_headers).json()
    assert preview["included_node_ids"] == []
    assert any("FinalMask" in warning for warning in preview["warnings"])
    public = client.get(f"/subscribe/clash/{token_response['token']}")
    assert public.status_code == 422
    assert public.json()["detail"]["code"] == "no_compatible_clash_nodes"
    decoded = base64.b64decode(
        client.get(f"/subscribe/v2ray/{token_response['token']}").text
    ).decode()
    assert json.loads(parse_qs(urlsplit(decoded).query)["fm"][0]) == FM
    # A masked node must not take down otherwise usable nodes in the subscription.
    added = client.post(
        "/api/v1/nodes/import",
        headers=admin_headers,
        json={"mode": "commit", "links": [uri(security="tls", sni="example.com")]},
    ).json()
    mixed = client.get(f"/subscribe/clash/{token_response['token']}")
    assert mixed.status_code == 200
    assert "FinalMask" in mixed.text
    assert len(yaml.safe_load(mixed.text)["proxies"]) == 1
    mixed_preview = client.get(
        f"/api/v1/subscriptions/{sub_id}/preview", headers=admin_headers
    ).json()
    assert mixed_preview["included_node_ids"] == [added["items"][0]["node_id"]]


@pytest.mark.parametrize(
    "params", [{"fm": "[]"}, {"fm": '{"tcp":{}}'}, {"fm": "invalid"}, {"pinSHA256": "bad-pin"}]
)
def test_invalid_options_atomic_import(client, admin_headers, params):
    result = client.post(
        "/api/v1/nodes/import",
        headers=admin_headers,
        json={"mode": "commit", "links": [uri(), uri(**params)], "atomic": True},
    ).json()
    assert result["created"] == 0
    assert result["failed"] == 1
    assert client.get("/api/v1/nodes/export", headers=admin_headers).json()["nodes"] == []


@pytest.mark.parametrize(
    "link", [uri(type="xhttp", fm=json.dumps(FM)), vmess_link(net="xhttp", fm=json.dumps(FM))]
)
def test_finalmask_preserved_for_vmess_and_vless(link):
    node = node_from_link(link)
    assert node_from_link(share_link(node, "test")).extra_json["finalmask"] == FM


def test_unknown_options_are_retained_and_warned(client, admin_headers):
    link = uri(type="grpc", mode="multi", future_option="required-handshake")
    result = client.post(
        "/api/v1/nodes/import", headers=admin_headers, json={"links": [link]}
    ).json()
    assert "future_option" in result["items"][0]["warning"]
    node = node_from_link(link)
    assert _clash_proxy(node, "test") is None
    query = parse_qs(urlsplit(share_link(node, "test")).query)
    assert query["future_option"] == ["required-handshake"]
    assert query["mode"] == ["multi"]


def test_supported_protocol_matrix_loads_in_mihomo(tmp_path):
    binary = os.environ.get("MIHOMO_BIN") or shutil.which("mihomo")
    if not binary:
        pytest.skip("Set MIHOMO_BIN to validate with a real Mihomo core")
    links = [
        uri(security="reality", pbk=KEY, sni="example.com", fp="chrome", flow="xtls-rprx-vision"),
        uri(
            "hysteria2",
            sni="example.com",
            pinSHA256=PIN,
            insecure=1,
            alpn="h3",
            mport="20443,20500-20505",
        ),
        uri("trojan", sni="example.com", alpn="h2,http/1.1", fp="chrome", allowInsecure=1),
        f"tuic://{UUID}:password@192.0.2.1:443?alpn=h3&congestion_control=bbr",
        "ss://YWVzLTEyOC1nY206cGFzc3dvcmQ@192.0.2.1:443?plugin=obfs-local%3Bobfs%3Dhttp%3Bobfs-host%3Dexample.com",
        "ss://2022-blake3-aes-128-gcm:AAAAAAAAAAAAAAAAAAAAAA%3D%3D@192.0.2.1:443",
        "ss://YWVzLTEyOC1nY206cGFzc3dvcmQ@192.0.2.1:443?plugin=v2ray-plugin%3Bmode%3Dwebsocket%3Btls%3Bhost%3Dexample.com%3Bpath%3D%2Ftest",
        uri(
            "hysteria2",
            obfs="gecko",
            **{"obfs-password": "password", "minPacketSize": 512, "maxPacketSize": 1200},
        ),
    ]
    for transport in ("ws", "grpc", "httpupgrade", "h2", "http"):
        links.append(
            uri(
                security="tls", type=transport, path="/test", host="example.com", alpn="h2,http/1.1"
            )
        )
        links.append(
            vmess_link(net=transport, path="/test", host="example.com", alpn="h2,http/1.1")
        )
    links.append(
        uri("trojan", security="tls", type="httpupgrade", path="/test", host="example.com")
    )
    proxies = [
        _clash_proxy(node_from_link(link), f"node-{index}") for index, link in enumerate(links)
    ]
    assert all(proxies)
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump({"proxies": proxies, "rules": ["MATCH,DIRECT"]}), encoding="utf-8"
    )
    result = subprocess.run(
        [binary, "-t", "-d", str(tmp_path), "-f", str(config)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert result.returncode == 0, result.stdout + result.stderr
