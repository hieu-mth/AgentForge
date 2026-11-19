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
