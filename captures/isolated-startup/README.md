# Isolated Startup Capture

- Stock Rovsun Wi-Fi module: disconnected before power-on
- Capture mode: receive-only; no monitor TX or VCC connected
- Baud/framing: 115200 8N1
- CP2102: COM6, connected to one UART signal; 1 byte captured
- Arduino Micro: COM12, connected to the other UART signal; 3770 bytes captured
- Capture duration: 90 seconds
- Raw streams: matching `.bin` files
- Chunk timestamps: matching `.tsv` files

The COM12 stream contains valid A5 `0x21` frames with `0C 0C` direction
Wi-Fi module was absent. The COM6 stream was effectively silent during this
run.
