# TODO

- [ ] Update `async_step_identify_grid_connect_uuid` to route to `async_step_select_fallback_uuid` when heuristic fails.
- [ ] Implement `async_step_select_fallback_uuid` to show all service UUIDs and allow user selection or re-scan.
- [ ] Add `async_step_wifi_credentials` to collect Wi‑Fi details and call `send_wifi_credentials`.
- [ ] Review `ble_wifi.py` for payload format and error codes.
- [ ] Review `const.py` for any legacy UUID constants.
