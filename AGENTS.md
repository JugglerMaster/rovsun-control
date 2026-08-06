# Agent Notes

## Timing Observation

- The AC beeps almost immediately after a button press.
- The unit then begins applying the requested setting.
- Approximately one second into that application, the app updates its displayed state.

This indicates that command delivery and physical response are faster than app
state confirmation. Reverse-engineering should capture both UART directions
with timestamps and distinguish the command, immediate acknowledgment, delayed
status report, and app polling or push-update delay.
