# Recovered OpenCode Captures

These receive-only paired captures were recovered from the local OpenCode
history. They are retained as raw `.bin` streams with matching timestamped
`.tsv` files. The source sessions used `115200 8N1` and recorded separate
signals on COM6, COM10, or COM12 depending on the hardware setup.

Included groups cover:

- Horizontal and vertical airflow transitions.
- Fan, mode, temperature, power, beep, light, drying, eco, sleep, and
  generator transitions.
- Connectivity, startup, and repeated state-change tests.

The original capture directory names are preserved so each transition remains
traceable to its original action. Cold-start captures containing the long
metadata frame are stored separately in `captures/cold-startup/`.

Review any capture for private metadata before publishing it outside this
repository. The recovered startup files were separately inspected and contain
the already-masked serial field described in their manifest.
