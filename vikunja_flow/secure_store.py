from __future__ import annotations

import platform
import subprocess
from abc import ABC, abstractmethod
from shutil import which
from typing import Optional


class SecretBackend(ABC):
    @abstractmethod
    def get_password(self, key: str) -> Optional[str]:
        raise NotImplementedError

    @abstractmethod
    def set_password(self, key: str, secret: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_password(self, key: str) -> None:
        raise NotImplementedError


class InMemorySecretBackend(SecretBackend):
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get_password(self, key: str) -> Optional[str]:
        return self._store.get(key)

    def set_password(self, key: str, secret: str) -> None:
        self._store[key] = secret

    def delete_password(self, key: str) -> None:
        self._store.pop(key, None)


class WindowsCredentialBackend(SecretBackend):
    def __init__(self, service_name: str) -> None:
        self._service = service_name
        self._cred = None
        self._ensure_win32()

    def _ensure_win32(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._advapi32 = ctypes.windll.advapi32

        class FILETIME(ctypes.Structure):
            _fields_ = [
                ("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD),
            ]

        class CREDENTIAL_ATTRIBUTEW(ctypes.Structure):
            _fields_ = [
                ("Keyword", wintypes.LPWSTR),
                ("Flags", wintypes.DWORD),
                ("ValueSize", wintypes.DWORD),
                ("Value", ctypes.c_void_p),
            ]

        class CREDENTIALW(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.c_void_p),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.POINTER(CREDENTIAL_ATTRIBUTEW)),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        self.FILETIME = FILETIME
        self.CREDENTIALW = CREDENTIALW
        self.LPCREDENTIALW = ctypes.POINTER(CREDENTIALW)
        self.wintypes = wintypes
        self.ctypes = ctypes

    def _target(self, key: str) -> str:
        return f"{self._service}:{key}"

    def get_password(self, key: str) -> Optional[str]:
        target = self._target(key)
        credential = self.LPCREDENTIALW()
        if not self._advapi32.CredReadW(target, 1, 0, self.ctypes.byref(credential)):
            return None
        try:
            blob = self.ctypes.string_at(credential.contents.CredentialBlob, credential.contents.CredentialBlobSize)
            return blob.decode("utf-16-le")
        finally:
            self._advapi32.CredFree(credential)

    def set_password(self, key: str, secret: str) -> None:
        target = self._target(key)
        blob_bytes = secret.encode("utf-16-le")
        buffer = self.ctypes.create_string_buffer(blob_bytes)
        credential = self.CREDENTIALW()
        credential.Flags = 0
        credential.Type = 1  # CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.CredentialBlobSize = self.ctypes.sizeof(buffer)
        credential.CredentialBlob = self.ctypes.cast(buffer, self.ctypes.c_void_p)
        credential.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE
        credential.AttributeCount = 0
        credential.Attributes = None
        credential.Comment = None
        credential.TargetAlias = None
        credential.UserName = None
        if not self._advapi32.CredWriteW(self.ctypes.byref(credential), 0):
            raise OSError("CredWriteW failed")

    def delete_password(self, key: str) -> None:
        target = self._target(key)
        self._advapi32.CredDeleteW(target, 1, 0)


class MacKeychainBackend(SecretBackend):
    def __init__(self, service_name: str) -> None:
        self._service = service_name

    def get_password(self, key: str) -> Optional[str]:
        try:
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-a",
                    key,
                    "-s",
                    self._service,
                    "-w",
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    def set_password(self, key: str, secret: str) -> None:
        subprocess.run(
            [
                "security",
                "add-generic-password",
                "-a",
                key,
                "-s",
                self._service,
                "-w",
                secret,
                "-U",
            ],
            check=True,
            capture_output=True,
        )

    def delete_password(self, key: str) -> None:
        subprocess.run(
            ["security", "delete-generic-password", "-a", key, "-s", self._service],
            check=False,
            capture_output=True,
        )


class SecretToolBackend(SecretBackend):
    def __init__(self, service_name: str) -> None:
        self._service = service_name

    def get_password(self, key: str) -> Optional[str]:
        try:
            result = subprocess.run(
                [
                    "secret-tool",
                    "lookup",
                    "service",
                    self._service,
                    "account",
                    key,
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            return result.stdout.strip() or None
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None

    def set_password(self, key: str, secret: str) -> None:
        try:
            process = subprocess.Popen(
                [
                    "secret-tool",
                    "store",
                    "--label",
                    f"{self._service} token",
                    "service",
                    self._service,
                    "account",
                    key,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("secret-tool not available; install libsecret tools") from exc
        stdout, stderr = process.communicate(secret)
        if process.returncode != 0:
            raise RuntimeError(f"secret-tool failed: {stderr}")

    def delete_password(self, key: str) -> None:
        try:
            subprocess.run(
                [
                    "secret-tool",
                    "clear",
                    "service",
                    self._service,
                    "account",
                    key,
                ],
                check=False,
                capture_output=True,
            )
        except FileNotFoundError:
            pass


class SecretStore:
    def __init__(self, service_name: str, backend: Optional[SecretBackend] = None) -> None:
        self._service = service_name
        self._backend = backend or self._detect_backend()

    def _detect_backend(self) -> SecretBackend:
        system = platform.system()
        if system == "Windows":
            try:
                return WindowsCredentialBackend(self._service)
            except Exception:
                return InMemorySecretBackend()
        if system == "Darwin":
            return MacKeychainBackend(self._service)
        if which("secret-tool"):
            return SecretToolBackend(self._service)
        return InMemorySecretBackend()

    def get_secret(self, key: str) -> Optional[str]:
        return self._backend.get_password(key)

    def set_secret(self, key: str, secret: str) -> None:
        self._backend.set_password(key, secret)

    def delete_secret(self, key: str) -> None:
        self._backend.delete_password(key)


__all__ = [
    "SecretStore",
    "SecretBackend",
    "InMemorySecretBackend",
]
