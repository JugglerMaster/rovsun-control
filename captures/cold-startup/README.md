# Cold Startup Captures

These are three repeat captures recovered from the local OpenCode history for
the `UART USB Device Connection Check` session. Each repeat contains both UART
directions at `115200 8N1`:

- `COM6`: main-board/AC-originated traffic, including full state reports and
  the long startup metadata frame.
- `COM12`: module-side traffic, including startup queries, acknowledgements,
  and short command frames.

The captures are receive-only recordings. No monitor TX was connected during
the startup capture. Raw `.bin` files are unchanged; matching `.tsv` files
contain chunk timestamps and hex bytes.

## Confirmed Startup Sequence

The first repeat shows the following approximate timing after power restore:

1. Around 4.965 s: `A5 01 00 21 ... 11 11` startup query.
2. Around 5.165 s: full `0x21` / `0C 0C` state reports begin.
3. Around 7.759 s: a 211-byte `A5 01 00 23` metadata frame appears.
4. The metadata contains `ACMCU/V9-R10FT27AC-FV001.001.030`.
5. Further `0x23` metadata/acknowledgement traffic and full state reports
   continue afterward.

The serial-number field in the metadata is already masked as `X` characters
in the captured device response. No Wi-Fi password, IP address, or MAC address
was identified during review.

The three repeats are retained because the startup order and metadata are
important for implementing a faithful AC emulator.
