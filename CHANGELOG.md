# Changelog

## 0.2.1 (2026-10-19)

### Added

- Imperva (utmvc): `session.imperva_utmvc(script_url, script, cookies)` returns `onestop.ImpervaResponse`; its payload is the `___utmvc` cookie value. Example: `examples/<client>/imperva_utmvc.py`.

## 0.2.0 (2026-10-20)

### Added

- Imperva (reese84): `session.imperva(script_url, script)` returns `onestop.ImpervaResponse`. Example: `examples/<client>/imperva.py`.

### Changed

- Akamai sensor: the pass is `_abck` containing `~0~` or the exact 17-byte `{"success": true}` reply (docs and examples).
- Kasada: each protected request sends the `x-kpsdk-h` from `mfc` and a fresh `x-kpsdk-cd` (docs and examples).
- TLS: use the newest Chrome profile the library has, and keep the User-Agent and `sec-ch-ua` on the latest Chrome (examples use Chrome 155).
- `timeout` bounds the whole call: connect, send and the full response read. A timeout raises `OneStopError` with `status_code` 0.

## 0.1.0 (2026-10-14)

Initial release.
