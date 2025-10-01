from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Optional

from .models import Profile
from .secure_store import SecretStore, SecretBackend


class ProfileNotFoundError(KeyError):
    pass


class ProfilesStore:
    def __init__(self, storage_path: Path, service_name: str = "vikunja_flow", secret_backend: Optional[SecretBackend] = None) -> None:
        self._storage_path = storage_path
        self._service_name = service_name
        self._secrets = SecretStore(service_name, backend=secret_backend)
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> Dict:
        if not self._storage_path.exists():
            return {"profiles": {}, "active": None}
        data = json.loads(self._storage_path.read_text("utf-8"))
        data.setdefault("profiles", {})
        data.setdefault("active", None)
        return data

    def _persist(self) -> None:
        self._storage_path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    def list_profiles(self) -> Iterable[str]:
        return sorted(self._state["profiles"].keys())

    def get_profile(self, name: str, include_secret: bool = True) -> Profile:
        raw = self._state["profiles"].get(name)
        if not raw:
            raise ProfileNotFoundError(name)
        profile = Profile(
            name=name,
            base_url=raw["base_url"],
            auth_method=raw["auth_method"],
            verify_tls=raw.get("verify_tls", True),
            default_list_id=raw.get("default_list_id"),
        )
        if include_secret:
            profile.token = self._secrets.get_secret(self._credential_key(name))
        return profile

    def set_active(self, name: str) -> None:
        if name not in self._state["profiles"]:
            raise ProfileNotFoundError(name)
        self._state["active"] = name
        self._persist()

    def active_profile_name(self) -> Optional[str]:
        return self._state.get("active")

    def get_active_profile(self) -> Profile:
        name = self.active_profile_name()
        if not name:
            raise ProfileNotFoundError("No active profile configured")
        return self.get_profile(name)

    def save_profile(self, profile: Profile, token: Optional[str]) -> None:
        data = {
            "base_url": profile.base_url.rstrip("/"),
            "auth_method": profile.auth_method,
            "verify_tls": profile.verify_tls,
            "default_list_id": profile.default_list_id,
        }
        self._state["profiles"][profile.name] = data
        if token:
            try:
                self._secrets.set_secret(self._credential_key(profile.name), token)
            except RuntimeError as exc:
                raise RuntimeError(f"Secure storage unavailable: {exc}") from exc
        elif profile.name in self._state["profiles"]:
            self._secrets.delete_secret(self._credential_key(profile.name))
        if not self._state.get("active"):
            self._state["active"] = profile.name
        self._persist()

    def remove_profile(self, name: str) -> None:
        if name in self._state["profiles"]:
            del self._state["profiles"][name]
            self._secrets.delete_secret(self._credential_key(name))
            if self._state.get("active") == name:
                self._state["active"] = next(iter(self._state["profiles"]), None)
            self._persist()
        else:
            raise ProfileNotFoundError(name)

    def _credential_key(self, profile_name: str) -> str:
        return f"{profile_name}::token"
