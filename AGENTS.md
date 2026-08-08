# Agent Notes

## Timing Observation

- The AC beeps almost immediately after a button press.
- The unit then begins applying the requested setting.
- Approximately one second into that application, the app updates its displayed state.

This indicates that command delivery and physical response are faster than app
state confirmation. Reverse-engineering should capture both UART directions
with timestamps and distinguish the command, immediate acknowledgment, delayed
status report, and app polling or push-update delay.

## Capture Retention

- Preserve useful raw UART captures in the repository for future protocol study;
  do not rely only on summarized README findings.
- Keep both UART directions when available, with separate files for each
  direction and the baud rate/framing in the filename.
- Include a short manifest or notes file recording the capture date, wiring,
  adapter/port, power state, exact app or remote action, and timestamps.
- Inspect captures before committing and remove or redact Wi-Fi credentials,
  local keys, MAC addresses, IP addresses, and other private metadata.
- Keep original packet bytes unchanged after sanitization; perform decoding on
  copies or through read-only tools.
- Use Git LFS when raw captures are too large for ordinary Git storage.
- Update the README with confirmed findings, but retain the corresponding raw
  capture so mappings and startup behavior remain reproducible.
