# Vikunja Flow

Vikunja Flow is a Flow Launcher plugin that lets you triage, search, and complete tasks from a self-hosted [Vikunja](https://vikunja.io) instance without leaving your keyboard.

## Installation

1. Install the plugin dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
2. Import the plugin folder into Flow Launcher (Settings → Plugins → Install from file) or package it for distribution.

The plugin registers the action keyword `vik`.

## Quick start

1. Create a [personal access token](https://tasks.dogiakos.com/api/v1/docs#/Auth/AuthTokenCreate) in Vikunja (recommended) or have your username/password ready.
2. In Flow Launcher, run:
   ```
   vik login work --url https://vikunja.example --token <paste-your-token>
   ```
   Optional flags:
   * `--verify-tls false` – skip TLS verification for trusted self-signed instances.
   * `--default-list <list_id>` – set the default list for `vik add`.
3. Switch instances at any time with `vik use <profile>`.

If you must authenticate with credentials, use:
```
vik login work --url https://vikunja.example --username you --password ********
```
The password is exchanged for an API token and never stored.

## Commands

| Command | Description |
| --- | --- |
| `vik login <profile> --url <base_url> --token <token>` | Add or update a profile. Use `--username`/`--password` instead of `--token` to exchange credentials for a token. |
| `vik use <profile>` | Switch the active profile. |
| `vik lists` | Show available lists (cached for 60 seconds). |
| `vik add "Task title" [--list "Inbox"] [--due YYYY-MM-DD] [--desc "Notes"]` | Create a task. Uses the profile default list if `--list` is omitted. |
| `vik find <search terms> [--page N]` | Search all tasks. A “Show more…” result autocompletes the next page. |
| `vik due today|tomorrow|week` | Review upcoming work. |
| `vik done <task_id>` | Mark a task complete. |
| `vik open <task_id>` | Retrieve details and open the task URL. |

Results support quick actions:
* **Enter** – open the task in your browser.
* **Alt** – run “Mark complete”.
* **Ctrl** – copy the task URL (if system clipboard integration is available).

## Profiles and security

Profiles are stored in `vikunja_flow/data/profiles.json`. Only non-secret metadata is written to disk. Tokens are saved in the OS credential manager: Windows uses the Credential Manager (DPAPI), macOS uses the Keychain via the `security` tool, and Linux uses `secret-tool` (libsecret). When no secure store is available the plugin falls back to in-memory secrets only.

Secrets are never logged. Switching profiles clears in-memory caches to prevent accidental leakage between instances.

## Development

### Project layout

```
vikunja_flow/
├── plugin.py          # Flow entry point and actions
├── router.py          # Command dispatcher and error handling
├── vikunja_client.py  # Typed Vikunja API client
├── profiles.py        # Encrypted profile persistence
├── parsers.py         # Command parsing helpers
├── models.py          # Shared dataclasses
├── mappers.py         # Flow result builders
```

### Tests

Run unit tests locally with:
```bash
pytest
```
A GitHub Actions workflow (`.github/workflows/tests.yml`) runs pytest on every push and pull request.

### Adding a new profile programmatically

```python
from vikunja_flow.models import Profile
from vikunja_flow.profiles import ProfilesStore

store = ProfilesStore(Path('vikunja_flow/data/profiles.json'))
profile = Profile('demo', 'https://vik.example', 'token', token='my-token')
store.save_profile(profile, profile.token)
```

## Security checklist

- [x] Tokens are stored exclusively in the OS credential vault (Windows Credential Manager, macOS Keychain, or libsecret).
- [x] Credentials are never echoed back to Flow or written to disk.
- [x] TLS verification is enabled by default and can be disabled per profile when necessary.
- [x] Commands validate inputs to avoid ambiguous list selections.

## Troubleshooting

* **401/403 errors** – refresh your token: `vik login <profile> --token <new-token>`.
* **TLS validation failed** – either fix the certificate chain or re-run login with `--verify-tls false` for trusted hosts.
* **Clipboard copy fails** – install a system clipboard tool (e.g., `pbcopy` on macOS, `xclip` on Linux) or enable Tk clipboard support.
