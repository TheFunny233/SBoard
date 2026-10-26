from __future__ import annotations

from typing import Any

# Share links use Xray's camelCase; Mihomo uses its own YAML schema.
_XHTTP_FIELDS = {
    "path": "path",
    "host": "host",
    "mode": "mode",
    "headers": "headers",
    "noGRPCHeader": "no-grpc-header",
    "xPaddingBytes": "x-padding-bytes",
    "xPaddingObfsMode": "x-padding-obfs-mode",
    "xPaddingKey": "x-padding-key",
    "xPaddingHeader": "x-padding-header",
    "xPaddingPlacement": "x-padding-placement",
    "xPaddingMethod": "x-padding-method",
    "uplinkHTTPMethod": "uplink-http-method",
    "sessionPlacement": "session-placement",
    "sessionKey": "session-key",
    "sessionTable": "session-table",
    "sessionLength": "session-length",
    "seqPlacement": "seq-placement",
    "seqKey": "seq-key",
    "uplinkDataPlacement": "uplink-data-placement",
    "uplinkDataKey": "uplink-data-key",
    "uplinkChunkSize": "uplink-chunk-size",
    "scMaxEachPostBytes": "sc-max-each-post-bytes",
    "scMinPostsIntervalMs": "sc-min-posts-interval-ms",
}
_XMUX_FIELDS = {
    "maxConcurrency": "max-concurrency",
    "maxConnections": "max-connections",
    "cMaxReuseTimes": "c-max-reuse-times",
    "hMaxRequestTimes": "h-max-request-times",
    "hMaxReusableSecs": "h-max-reusable-secs",
    "hKeepAlivePeriod": "h-keep-alive-period",
}


def validate_xhttp_extra(settings: Any) -> None:
    if not isinstance(settings, dict):
        # Pydantic validators must raise ValueError to produce a validation response.
        raise ValueError("XHTTP extra must be a JSON object")  # noqa: TRY004
    for key in ("headers", "xmux", "downloadSettings"):
        if key in settings and not isinstance(settings[key], dict):
            raise ValueError(f"XHTTP {key} must be an object")
    download = settings.get("downloadSettings", {})
    for key in ("xhttpSettings", "realitySettings", "tlsSettings"):
        if key in download and not isinstance(download[key], dict):
            raise ValueError(f"XHTTP downloadSettings.{key} must be an object")
    transport = download.get("xhttpSettings", {})
    for key in ("headers", "xmux"):
        if key in transport and not isinstance(transport[key], dict):
            raise ValueError(f"XHTTP downloadSettings.xhttpSettings.{key} must be an object")
    security = download.get("security")
    if security is not None and security not in ("none", "tls", "reality"):
        raise ValueError("unsupported XHTTP downloadSettings.security")
    if download.get("network", "xhttp") != "xhttp":
        raise ValueError("only XHTTP downloadSettings.network is supported")


def _mapped(source: dict[str, Any], fields: dict[str, str]) -> dict[str, Any]:
    return {target: source[key] for key, target in fields.items() if source.get(key) is not None}


def _transport_options(settings: dict[str, Any]) -> dict[str, Any]:
    options = _mapped(settings, _XHTTP_FIELDS)
    xmux = settings.get("xmux")
    if isinstance(xmux, dict):
        options["reuse-settings"] = _mapped(xmux, _XMUX_FIELDS)
    return options


def clash_xhttp_options(
    path: str | None, host: str | None, extra: dict[str, Any]
) -> dict[str, Any]:
    settings = extra.get("xhttp_extra") or {}
    options = _transport_options(settings)
    for key, value in {"path": path, "host": host, "mode": extra.get("xhttp_mode")}.items():
        if value is not None:
            options[key] = value

    download = settings.get("downloadSettings")
    if isinstance(download, dict):
        transport = download.get("xhttpSettings") or {}
        # Download mode inherits the uplink mode in Mihomo; only these
        # transport fields can be overridden on the download connection.
        down = {
            key: value
            for key, value in _transport_options(transport).items()
            if key in {"path", "host", "headers", "reuse-settings"}
        }
        down.update(_mapped(download, {"address": "server", "port": "port"}))
        if "security" in download:
            down["tls"] = download["security"] in {"tls", "reality"}
            # An explicitly non-Reality download must not inherit uplink Reality.
            if download["security"] != "reality":
                down["reality-opts"] = {}
        tls = download.get("tlsSettings") or {}
        reality = download.get("realitySettings") or {}
        down.update(
            _mapped(
                tls,
                {
                    "serverName": "servername",
                    "alpn": "alpn",
                    "fingerprint": "client-fingerprint",
                    "allowInsecure": "skip-cert-verify",
                },
            )
        )
        down.update(
            _mapped(reality, {"serverName": "servername", "fingerprint": "client-fingerprint"})
        )
        if reality:
            down["reality-opts"] = _mapped(
                reality,
                {"publicKey": "public-key", "shortId": "short-id", "spiderX": "spider-x"},
            )
            # A download reality-opts replaces the entire uplink object, so the
            # compatibility flag must be copied here as well as on the uplink.
            down["reality-opts"]["support-x25519mlkem768"] = extra.get(
                "reality_support_x25519mlkem768", True
            )
        options["download-settings"] = down
    return options
