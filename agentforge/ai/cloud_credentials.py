"""Protect Owner credentials with Windows user-scoped DPAPI."""
import base64
import ctypes
from ctypes import wintypes
import sys


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.c_void_p)]


def protect_api_key(key):
    if sys.platform != "win32":
        raise ValueError("Lưu API key trực tiếp cần Windows. Hãy dùng biến môi trường.")
    data = ctypes.create_string_buffer(key.encode("ascii"))
    source = _Blob(len(key), ctypes.addressof(data))
    encrypted = _Blob()
    protect = ctypes.windll.crypt32.CryptProtectData
    protect.argtypes = [ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.c_void_p,
                        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                        ctypes.POINTER(_Blob)]
    free = ctypes.windll.kernel32.LocalFree
    free.argtypes = [ctypes.c_void_p]
    free.restype = ctypes.c_void_p
    try:
        if not protect(ctypes.byref(source), "AgentForge API key", None, None, None,
                       1, ctypes.byref(encrypted)):
            raise ValueError("Windows không thể mã hóa API key cho tài khoản hiện tại.")
        return base64.b64encode(ctypes.string_at(encrypted.data, encrypted.size)).decode("ascii")
    finally:
        ctypes.memset(data, 0, len(data))
        if encrypted.data:
            free(encrypted.data)


def unprotect_api_key(protected):
    """Decrypt only for a request, under the original Windows account."""
    if sys.platform != "win32":
        raise ValueError("API key đã mã hóa cần tài khoản Windows ban đầu.")
    try:
        raw = base64.b64decode(protected, validate=True)
    except (ValueError, TypeError):
        raise ValueError("Không đọc được API key đã mã hóa.") from None
    data = ctypes.create_string_buffer(raw)
    source = _Blob(len(raw), ctypes.addressof(data))
    decrypted = _Blob()
    unprotect = ctypes.windll.crypt32.CryptUnprotectData
    unprotect.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                          ctypes.POINTER(_Blob)]
    free = ctypes.windll.kernel32.LocalFree
    free.argtypes = [ctypes.c_void_p]
    free.restype = ctypes.c_void_p
    try:
        if not unprotect(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(decrypted)):
            raise ValueError("Không giải mã được API key bằng tài khoản hiện tại.")
        return ctypes.string_at(decrypted.data, decrypted.size).decode("ascii")
    finally:
        if decrypted.data:
            ctypes.memset(decrypted.data, 0, decrypted.size)
            free(decrypted.data)
