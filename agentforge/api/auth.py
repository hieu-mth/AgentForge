"""Single-Owner session and cookie operations; HTTP Host/Origin checks stay in transport."""
import hmac
import secrets
import time
from http import cookies

COOKIE = "af_owner_session"
SESSION_SECONDS = 8 * 60 * 60
SENSITIVE_GRANTS = {"model.invoke", "network.read", "network.search",
                    "browser.run", "process.run"}
LOCAL_GRANTS = {"workspace.write", "workspace.propose", "workspace.read"}


def get_session(self):
    raw = self.headers.get("Cookie", "")
    if len(raw) > 2048:
        return None
    try:
        jar = cookies.SimpleCookie()
        jar.load(raw)
        item = jar.get(COOKIE)
    except cookies.CookieError:
        return None
    if item is None:
        return None
    with self.server.auth_lock:
        session = self.server.sessions.get(item.value)
        if session and session["expires"] > time.monotonic():
            return session
    return None


def login(self, data):
    code = data.get("code")
    if not isinstance(code, str) or len(code) > 128:
        return self._blocked(401, "invalid_credentials")
    with self.server.auth_lock:
        now = time.monotonic()
        self.server.failed_logins = [
            at for at in self.server.failed_logins if now - at < 60]
        if len(self.server.failed_logins) >= 5:
            return self._blocked(429, "login_rate_limited")
        if not hmac.compare_digest(code, self.server.owner_code):
            self.server.failed_logins.append(now)
            return self._blocked(401, "invalid_credentials")
        session_id = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        self.server.sessions[session_id] = {
            "csrf": csrf, "expires": now + SESSION_SECONDS}
    return self._reply(200, {"status": "AUTHENTICATED", "csrf": csrf},
                       headers=(("Set-Cookie", f"{COOKIE}={session_id}; "
                                 "HttpOnly; SameSite=Strict; Path=/; "
                                 f"Max-Age={SESSION_SECONDS}"),))


def logout(self):
    with self.server.auth_lock:
        jar = cookies.SimpleCookie()
        jar.load(self.headers.get("Cookie", ""))
        item = jar.get(COOKIE)
        if item:
            self.server.sessions.pop(item.value, None)
    return self._reply(200, {"status": "LOGGED_OUT"},
                       headers=(("Set-Cookie", f"{COOKIE}=; "
                                 "HttpOnly; SameSite=Strict; Path=/; Max-Age=0"),))
