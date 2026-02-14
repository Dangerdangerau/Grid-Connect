# Grid Connect Device Internet Connection Process (Behind the Scenes)

This document explains what happens step-by-step when a Grid Connect device is onboarded and gets internet access through this integration.

## 1. User starts onboarding in Home Assistant

1. The user opens the Grid Connect config flow (`config_flow.py`).
2. The flow offers:
   - BLE scan (`action = "scan"`)
   - Manual entry (`action = "manual"`)
3. If scan is selected, Home Assistant scans for nearby BLE advertisements for about 10 seconds.

Protocols involved:
- BLE advertising (Bluetooth Low Energy broadcast packets).
- Home Assistant Bluetooth discovery API.

## 2. BLE device discovery and selection

1. The integration collects discovered devices and their advertised `service_uuids`.
2. The user selects one device by BLE MAC address.
3. The integration tries to identify a likely Grid Connect service UUID.
4. If auto-detection fails, the user manually selects a fallback UUID from the advertised list.

Protocols involved:
- BLE GAP for discovery and identification.
- BLE GATT service UUID metadata for capability detection.

## 3. Wi-Fi credentials are collected

1. After device selection, the flow asks for:
   - `ssid`
   - `password`
2. These credentials are not sent over IP yet. They are prepared for BLE provisioning first.

## 4. Wi-Fi credentials are sent over BLE GATT

1. `send_wifi_credentials()` in `ble_wifi.py` is called.
2. The integration writes data to a BLE characteristic:
   - Service UUID (placeholder): `0000fd88-0000-1000-8000-00805f9b34fb`
   - Write characteristic UUID (placeholder): `0000fd89-0000-1000-8000-00805f9b34fb`
3. Payload format used right now is:
   - `"<ssid>,<password>"` encoded as bytes.
4. The write uses `response=True`, so the BLE layer expects a GATT write response.

Protocols involved:
- BLE GATT Write Request / Write Response (ATT over BLE link).

## 5. Device joins the Wi-Fi network

1. The device firmware receives SSID/password from BLE.
2. The device exits onboarding mode and starts 802.11 association to the access point.
3. It runs standard network bootstrap:
   - 802.11 authentication/association
   - DHCP for IP, gateway, DNS
4. Once connected, the device can reach LAN services and internet routes allowed by the router/firewall.

Protocols involved:
- IEEE 802.11 (Wi-Fi)
- DHCP
- DNS
- IP routing/NAT at router

## 6. Wi-Fi encryption details (what protects traffic)

Expected Wi-Fi protection on the air interface:
- WPA2-Personal (AES-CCMP) or WPA3-SAE, depending on router + device support.
- If router is open/weakly configured, radio traffic protection is reduced.

Important distinction:
- Wi-Fi encryption protects device↔router radio frames after Wi-Fi join.
- It does not automatically secure how credentials are handled before join.

## 7. BLE security details during credential provisioning

Current integration behavior:
- The payload is plain text `ssid,password` before write.
- No application-layer encryption is applied in `ble_wifi.py`.

Security outcome depends on BLE pairing mode:
- If BLE link is encrypted/authenticated (paired/bonded), credentials are protected in transit.
- If BLE link is not encrypted, provisioning can be exposed to local attackers in range.

## 8. What happens after provisioning in this project

1. On successful BLE credential write, a Home Assistant config entry is created with:
   - device BLE address
   - selected Grid Connect UUID
   - device name
   - Wi-Fi SSID
2. Runtime communication APIs in this repo are still mostly stubs (`api.py`, `local_api.py`), so cloud/local operational protocol details after Wi-Fi join are not fully implemented yet.

## 9. Failure points and protocol-level causes

- No BLE devices found:
  - device not in pairing mode
  - weak BLE signal
  - adapter or scan permission issues
- BLE write failure:
  - wrong UUID/characteristic
  - not connected at BLE transport level
  - timeout in ATT/GATT operation
- Wi-Fi join failure on device side:
  - wrong SSID/password
  - unsupported Wi-Fi band/security mode
  - DHCP or router ACL restrictions

## 10. Security hardening recommendations

1. Require BLE pairing + bonding before credential write.
2. Replace plain payload with encrypted provisioning blob (application-layer crypto).
3. Use per-device ephemeral onboarding keys or challenge-response.
4. Avoid persisting cleartext secrets in logs/state.
5. Prefer WPA3-SAE where possible; otherwise WPA2-AES only.

---

In short: this integration currently provisions Wi-Fi by sending SSID/password over BLE GATT, then the device performs normal Wi-Fi/DHCP/IP internet onboarding. The strongest protection depends on BLE link security during provisioning and WPA2/WPA3 security after Wi-Fi association.
