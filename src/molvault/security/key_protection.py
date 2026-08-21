"""Windows DPAPI protection for retained package keys."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def protect_key(key: bytes, *, entropy: bytes) -> bytes:
    """Protect key material with machine-scoped Windows DPAPI."""
    if sys.platform != "win32":
        raise RuntimeError("Windows DPAPI is required to protect package keys")
    input_buffer = ctypes.create_string_buffer(key)
    entropy_buffer = ctypes.create_string_buffer(entropy)
    input_blob = _DataBlob(len(key), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    entropy_blob = _DataBlob(
        len(entropy), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte))
    )
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    # CRYPTPROTECT_LOCAL_MACHINE permits authorized staff accounts on this workstation.
    if not crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        "MolKey package key",
        ctypes.byref(entropy_blob),
        None,
        None,
        0x4,
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def unprotect_key(protected: bytes, *, entropy: bytes) -> bytes:
    """Recover key material protected by :func:`protect_key`."""
    if sys.platform != "win32":
        raise RuntimeError("Windows DPAPI is required to recover package keys")
    protected_buffer = ctypes.create_string_buffer(protected)
    entropy_buffer = ctypes.create_string_buffer(entropy)
    protected_blob = _DataBlob(
        len(protected), ctypes.cast(protected_buffer, ctypes.POINTER(ctypes.c_ubyte))
    )
    entropy_blob = _DataBlob(
        len(entropy), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte))
    )
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    if not crypt32.CryptUnprotectData(
        ctypes.byref(protected_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)
