# Mini Cyberdeck OS

CircuitPython-based CyberDeck operating system for the Waveshare ESP32-S3 Touch LCD 2.8" (240x320 portrait).

## Hardware

- **Display**: Waveshare ESP32-S3 Touch LCD 2.8" (240x320, portrait)
- **Audio**: I2S audio output
- **Input**: Touch screen + external USB keyboard (KMK firmware)

## Features

- App launcher with swipe/tap navigation
- Multiple built-in apps including Digital Pet, Mini Synth, Notes, BLE Scanner, and more
- Theme system (green, amber, red, purple, grey, paper)
- External keyboard support (arrow keys, ESC, enter)
- Sound effects and audio synthesis

## Apps

| App | Description |
|-----|-------------|
| DIGITAL PET | Hatch and raise a pixel monster companion |
| MINI SYNTH | 8-note honeycomb keyboard synthesizer |
| NOTES | T9-style text notes |
| BLE SCANNER | Scan for nearby BLE devices |
| NETWORK | WiFi status and network info |
| CLOCK | Digital clock display |
| THEMES | Theme selector |
| TOUCH TEST | Touch gesture visualizer |
| HELLO WORLD | Terminal greeting |
| ACCELEROMETER | Accelerometer data display |

## Setup

1. Copy contents to CIRCUITPY drive (D:\)
2. Edit `settings.toml` with your WiFi credentials
3. Apps are loaded from `/sd/apps/`

## Controls

- **Tap**: Select/open
- **Swipe up**: Back/quit
- **Swipe down**: Refresh (in launcher)
- **Arrow keys**: Navigate menu (with external keyboard)
- **ESC**: Quit app
