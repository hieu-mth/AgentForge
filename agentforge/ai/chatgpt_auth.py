"""Local, Owner-controlled Sign in with ChatGPT. No browser session scraping."""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import time
from urllib.parse import parse_qs, urlencode, urlsplit
import uuid
import webbrowser

from agentforge.ai import cloud_credentials
from agentforge.paths import ensure_local_root

ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
SCOPE = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
ACCOUNT_RE = re.compile(r"[a-z][a-z0-9_]{2,39}\Z")
DB_PATH = Path.home() / ".agentforge" / "chatgpt.sqlite3"


class AuthError(ValueError):
    pass


def _require_windows():
    if sys.platform != "win32":
        raise AuthError("ChatGPT sign-in requires Windows DPAPI.")


@contextmanager
def _db():
    _require_windows()
    path = ensure_local_root(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=120)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS host (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS accounts (ref TEXT PRIMARY KEY, encrypted TEXT NOT NULL)")
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ref(ref):
    if not isinstance(ref, str) or not ACCOUNT_RE.fullmatch(ref):
        raise AuthError("Invalid ChatGPT account reference.")
    return ref


def _load(conn, ref):
    row = conn.execute("SELECT encrypted FROM accounts WHERE ref=?", (_ref(ref),)).fetchone()
    return json.loads(cloud_credentials.unprotect_api_key(row[0])) if row else {}


def _save(conn, ref, data):
    protected = cloud_credentials.protect_api_key(json.dumps(data, ensure_ascii=True, separators=(",", ":")))
    conn.execute("INSERT OR REPLACE INTO accounts VALUES (?,?)", (_ref(ref), protected))


def _host(conn):
    row = conn.execute("SELECT id FROM host").fetchone()
    if row:
        return row[0]
    host = "urn:uuid:" + str(uuid.uuid4())
    conn.execute("INSERT INTO host VALUES (?)", (host,))
    return host


def _http(host, method, path, *, form=None, token=None):
    conn = http.client.HTTPSConnection(host, timeout=45)
    headers = {"Accept": "application/json"}
    body = None
    if form is not None:
        body = urlencode(form).encode("ascii")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        if response.status != 200:
            raise AuthError("ChatGPT HTTP " + str(response.status) + "; reconnect or check usage.")
        raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise AuthError("ChatGPT response too large.")
        return json.loads(raw) if raw else {}
    except (OSError, http.client.HTTPException, ValueError) as exc:
        if isinstance(exc, AuthError):
            raise
        raise AuthError("ChatGPT authorization or catalog request failed.") from None
    finally:
        conn.close()


def _token(form):
    return _http("auth.openai.com", "POST", "/api/accounts/oauth/token", form={**form, "resource": RESOURCE})


def _verify_identity(token, client, nonce):
    try:
        import jwt
    except ImportError:
        raise AuthError('Install the optional chatgpt dependency: pip install -e ".[chatgpt]"') from None
    try:
        metadata = _http("auth.openai.com", "GET", "/.well-known/openid-configuration")
        uri = urlsplit(metadata["jwks_uri"])
        if (uri.scheme, uri.netloc) != ("https", "auth.openai.com") or uri.query or uri.fragment:
            raise AuthError("Unexpected OpenAI JWKS endpoint.")
        jwks = _http("auth.openai.com", "GET", uri.path)
        header = jwt.get_unverified_header(token)
        keys = [key for key in jwks["keys"] if key.get("kid") == header.get("kid")]
        if len(keys) != 1 or header.get("alg") != "RS256":
            raise AuthError("Unsupported OpenAI ID token signature.")
        key = jwt.PyJWK.from_dict(keys[0], algorithm="RS256").key
        claims = jwt.decode(token, key, algorithms=["RS256"], issuer=ISSUER, audience=client,
                            options={"require": ["exp", "iss", "aud", "sub", "nonce"]})
        if not hmac.compare_digest(claims["nonce"], nonce):
            raise AuthError("Invalid ChatGPT ID token nonce.")
        if not isinstance(claims["sub"], str) or not claims["sub"]:
            raise AuthError("Invalid ChatGPT account identity.")
        return claims
    except Exception:
        raise AuthError("Could not verify ChatGPT ID token.") from None


def _credentials(data, previous=None):
    previous = previous or {}
    scopes = data.get("scope", previous.get("scope", ""))
    access = data.get("access_token")
    refresh = data.get("refresh_token", previous.get("refresh_token"))
    expires = data.get("expires_in")
    if (not isinstance(scopes, str) or not {PLAN_SCOPE, "resource.invoke"}.issubset(scopes.split())
            or not isinstance(access, str) or not re.fullmatch(r"[!-~]{1,32768}", access)
            or not isinstance(refresh, str) or not re.fullmatch(r"[!-~]{1,32768}", refresh)
            or type(expires) is not int or not 1 <= expires <= 86400 * 30
            or str(data.get("token_type", "")).lower() != "bearer"):
        raise AuthError("ChatGPT plan permission or renewable credentials unavailable.")
    return {"access_token": access, "refresh_token": refresh, "scope": scopes,
            "expires_at": int(time.time()) + expires}


def _callback(query, state, old_client):
    if any(len(v) != 1 for v in query.values()):
        raise AuthError("Duplicate OAuth callback parameters.")
    values = {key: value[0] for key, value in query.items()}
    if not hmac.compare_digest(values.get("state", ""), state):
        raise AuthError("Invalid OAuth state.")
    if "error" in values:
        raise AuthError("ChatGPT authorization declined.")
    client = values.get("client_id", old_client)
    if (not isinstance(client, str) or not re.fullmatch(r"oaiapp_[A-Za-z0-9_-]{1,256}", client)
            or (old_client and old_client != client) or not values.get("code")):
        raise AuthError("Incomplete or mismatched OAuth registration.")
    return client, values["code"]


def sign_in(ref):
    """Explicit local browser sign-in, one pending attempt, no tokens printed."""
    _ref(ref)
    _require_windows()
    try:
        import jwt  # noqa: F401
    except ImportError:
        raise AuthError('Install the optional chatgpt dependency: pip install -e ".[chatgpt]"') from None
    with _db() as conn:
        previous = _load(conn, ref)
        host_id = _host(conn)
    old_client = previous.get("client_id")
    state, nonce, verifier = (secrets.token_urlsafe(48) for _ in range(3))
    outcome = {}

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(5)
            super().setup()

        def log_message(self, *_args):
            pass

        def do_GET(self):
            path = urlsplit(self.path)
            if (path.path != "/auth/callback" or
                    self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}"):
                self.send_error(404)
                return
            try:
                query = parse_qs(path.query, max_num_fields=20)
                if query.get("state") != [state]:
                    raise AuthError("Invalid OAuth state.")
                outcome["query"] = query
                self.send_response(200)
                message = b"AgentForge received the sign-in callback. Return to AgentForge."
            except (ValueError, AuthError):
                self.send_response(400)
                message = b"Invalid sign-in callback."
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        redirect = f"http://127.0.0.1:{server.server_port}/auth/callback"
        params = {"client_id": old_client or "dynamic_agent_client", "ext_agent_host_id": host_id,
                  "response_type": "code", "redirect_uri": redirect, "scope": SCOPE,
                  "resource": RESOURCE, "state": state, "nonce": nonce,
                  "code_challenge_method": "S256",
                  "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")}
        if old_client:
            if previous.get("id_token"):
                params["id_token_hint"] = previous["id_token"]
        else:
            params["agent_name_hint"] = "AgentForge"
        if not webbrowser.open(ISSUER + "/api/accounts/authorize?" + urlencode(params)):
            raise AuthError("Could not open the system browser.")
        deadline = time.monotonic() + 180
        server.timeout = 1
        while "query" not in outcome and time.monotonic() < deadline:
            server.handle_request()
    if "query" not in outcome:
        raise AuthError("ChatGPT sign-in timed out.")
    client, code = _callback(outcome["query"], state, old_client)
    with _db() as conn:
        if _load(conn, ref) != previous:
            raise AuthError("Account changed during sign-in; retry.")
        if not old_client:
            _save(conn, ref, {"client_id": client})
    data = _token({"grant_type": "authorization_code", "client_id": client, "code": code,
                   "code_verifier": verifier, "redirect_uri": redirect})
    identity = _verify_identity(data.get("id_token"), client, nonce)
    if previous.get("subject") and identity["sub"] != previous["subject"]:
        raise AuthError("The returned account does not match this registration.")
    record = {"client_id": client, "subject": identity["sub"], "email": identity.get("email", ""),
              "id_token": data["id_token"], **_credentials(data)}
    with _db() as conn:
        expected = previous if old_client else {"client_id": client}
        if _load(conn, ref) != expected:
            raise AuthError("Account changed during sign-in; retry.")
        _save(conn, ref, record)
    return {"account_ref": ref, "email": record["email"], "plan_usage": True}


def access_token(ref):
    # SQLite write transaction serializes rotating refresh tokens across CLI and Studio.
    with _db() as conn:
        record = _load(conn, ref)
        if not {PLAN_SCOPE, "resource.invoke"}.issubset(record.get("scope", "").split()):
            raise AuthError("ChatGPT plan usage not connected.")
        if record["expires_at"] <= time.time() + 90:
            data = _token({"grant_type": "refresh_token", "client_id": record["client_id"],
                           "refresh_token": record["refresh_token"]})
            record.update(_credentials(data, record))
            _save(conn, ref, record)
        return record["access_token"]


def models(ref):
    response = _http("api.openai.com", "GET", "/v1/models", token=access_token(ref))
    if not isinstance(response.get("models"), list):
        raise AuthError("Unexpected ChatGPT model catalog.")
    return [{"slug": x["slug"], "display_name": x.get("display_name", x["slug"])}
            for x in response["models"] if isinstance(x, dict) and x.get("visibility") == "list"
            and isinstance(x.get("slug"), str)]


def sign_out(ref):
    with _db() as conn:
        record = _load(conn, ref)
        if not record:
            return {"remote_revocation": "NOT_CONNECTED"}
        revoked = False
        try:
            if record.get("refresh_token"):
                meta = _http("auth.openai.com", "GET", "/.well-known/openid-configuration")
                uri = urlsplit(meta["revocation_endpoint"])
                if (uri.scheme, uri.netloc) == ("https", "auth.openai.com") and not uri.query and not uri.fragment:
                    _http("auth.openai.com", "POST", uri.path,
                          form={"token": record["refresh_token"], "token_type_hint": "refresh_token",
                                "client_id": record["client_id"]})
                    revoked = True
        except (ValueError, KeyError):
            pass
        _save(conn, ref, {k: record[k] for k in ("client_id", "subject", "email") if k in record})
        return {"remote_revocation": "CONFIRMED" if revoked else "NOT_CONFIRMED",
                "local_credentials_cleared": True}


def main():
    parser = argparse.ArgumentParser(description="AgentForge local ChatGPT connection")
    parser.add_argument("action", choices=["login", "models", "probe", "logout"])
    parser.add_argument("account")
    parser.add_argument("--model")
    args = parser.parse_args()
    try:
        if args.action == "login":
            result = sign_in(args.account)
        elif args.action == "models":
            result = models(args.account)
        elif args.action == "logout":
            result = sign_out(args.account)
        else:
            if not args.model or args.model not in {m["slug"] for m in models(args.account)}:
                raise AuthError("Choose an available model from the models command.")
            from agentforge.features.film_studio import studio_chatgpt
            result = studio_chatgpt.probe({"provider": "chatgpt", "account_ref": args.account, "model": args.model})
        print(json.dumps(result, ensure_ascii=True))
    except AuthError as exc:
        # AuthError is constructed only from local fixed messages and HTTP status integers.
        parser.exit(1, "ChatGPT authentication: " + str(exc) + "\n")
    except (ValueError, sqlite3.Error, OSError, KeyError, TypeError) as exc:
        from agentforge.features.film_studio.studio_cloud import CloudRequestError
        if isinstance(exc, CloudRequestError) and re.fullmatch(r"[A-Z_0-9]{1,64}", exc.code):
            parser.exit(1, "ChatGPT inference: " + exc.code + "\n")
        parser.exit(1, "ChatGPT action failed (" + type(exc).__name__ + "); no tokens printed.\n")


if __name__ == "__main__":
    main()
