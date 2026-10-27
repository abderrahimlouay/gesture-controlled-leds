# Hand Gesture LED Controller

Control 5 LEDs on an **Arduino Uno R3** with your fingers, in real time, using your laptop's built-in camera.

**Finger open = LED on. Finger closed = LED off. No hand detected = all LEDs off.**

Built with **Python**, **OpenCV**, **MediaPipe Hands** and **PySerial**.

## How it works

```
Laptop camera ──► OpenCV (capture + overlay)
                      │
                      ▼
             MediaPipe Hands (21 landmarks)
                      │
                      ▼
        Open/closed per finger (distance-based)
                      │
                      ▼
     Smoothing (majority vote over last 5 frames)
                      │
                      ▼
     1 byte over USB serial (bit0..bit4 = thumb..pinky)
                      │
                      ▼
          Arduino Uno ──► 5 LEDs
```

- **Finger detection:** for index, middle, ring and pinky, a finger is *open* when its tip is farther from the wrist than its middle joint (PIP). The thumb compares its tip and IP joint distances to the base of the pinky. Because it uses distances instead of "tip above joint", it works even when your hand is tilted or sideways.
- **Smoothing:** a majority vote over the last 5 frames removes flicker.
- **Protocol:** a single byte per update. Bits 0-4 map to thumb, index, middle, ring, pinky. It is sent on change plus a heartbeat every 0.5 s.
- **Failsafe:** if the Arduino receives nothing for 1.5 s (script crashed, cable unplugged), all LEDs turn off.

## Project structure

```
.
├── finger_leds/
│   └── finger_leds.ino   # Arduino sketch
├── hand_leds.py          # Python: camera, detection, serial
├── requirements.txt
└── README.md
```

> The Arduino IDE requires the `.ino` file to live in a folder with the same name (`finger_leds/finger_leds.ino`).

## Hardware

- Arduino Uno R3 + USB cable
- 5 LEDs
- 5 resistors, 220 ohm (330 ohm also works)
- Breadboard and jumper wires

### Pin mapping

| Finger | Arduino pin | Bit |
|--------|-------------|-----|
| Thumb  | D2 | 0 |
| Index  | D3 | 1 |
| Middle | D4 | 2 |
| Ring   | D5 | 3 |
| Pinky  | D6 | 4 |

### Wiring

Each LED uses the same chain:

```
Arduino pin ──► resistor (220Ω) ──► LED long leg (+, anode)
                                    LED short leg (–, cathode) ──► GND
```

1. Connect the Arduino **GND** to the breadboard's ground rail.
2. Place each LED in its own row, with the **short leg (flat side)** going to the ground rail.
3. Connect a resistor from the LED's long-leg row to a free row, then a jumper from that row to the matching Arduino pin.

The resistor is mandatory. Without it the LED (and possibly the pin) can burn out.

## Installation

### 1. Arduino

1. Open `finger_leds/finger_leds.ino` in the Arduino IDE.
2. Select **Board: Arduino Uno** and the correct port.
3. Upload. On boot, the LEDs should light up one after another. If they do, the wiring is correct.

### 2. Python

Requires **Python 3.9 - 3.12** (MediaPipe 0.10.x does not support newer versions).

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Linux extras:**

```bash
sudo apt install libportaudio2                 # needed by MediaPipe's audio import
sudo usermod -aG dialout $USER                 # serial port access; log out and back in after
```

#### Slow or unstable internet?

MediaPipe pulls in large dependencies (`jax`, `jaxlib`, about 90 MB) that hand tracking does not use. Skip them:

```bash
pip install --default-timeout=300 --retries 20 "numpy<2" opencv-contrib-python==4.10.0.84 pyserial
pip install --default-timeout=300 --retries 20 --no-deps mediapipe==0.10.14
pip install --default-timeout=300 --retries 20 absl-py attrs flatbuffers "protobuf>=4.25.3,<5" matplotlib sounddevice
```

pip caches finished downloads, so re-running a command after a timeout resumes where it stopped.

## Usage

Close the Arduino IDE Serial Monitor first (it locks the port), then:

```bash
python hand_leds.py                        # auto-detects the Arduino
python hand_leds.py --port /dev/ttyACM0    # Linux
python hand_leds.py --port COM3            # Windows
python hand_leds.py --no-serial            # vision only, no Arduino needed
python hand_leds.py --camera 1             # use another camera
python hand_leds.py --no-mirror            # don't flip the preview
```

Press `q` or `Esc` in the video window to quit. The LEDs are turned off on exit.

### Command-line options

| Option | Description | Default |
|--------|-------------|---------|
| `--port` | Serial port of the Arduino | auto-detect |
| `--baud` | Baud rate (must match the sketch) | 115200 |
| `--camera` | Camera index | 0 |
| `--no-serial` | Run without an Arduino | off |
| `--no-mirror` | Disable mirrored preview | off |

## Tuning

At the top of `hand_leds.py`:

- `OPEN_RATIO` (default `1.05`): raise it (e.g. `1.15`) if closed fingers read as open; lower it if open fingers read as closed.
- `SMOOTH_FRAMES` (default `5`): higher is steadier but slightly laggier.
- `HEARTBEAT_S` (default `0.5`): must stay well below the Arduino's 1.5 s timeout.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `No Arduino found` | Check the cable, pass `--port` manually. |
| `Could not open port` / permission denied | Close the Serial Monitor; on Linux add yourself to `dialout`. |
| LED never lights up | Flip it around (polarity matters) and check the resistor and pin. |
| `Cannot open camera` | Try `--camera 1`, and make sure no other app is using the camera. |
| Unstable detection | Good front lighting, plain background, palm facing the camera, 40-80 cm away. |
| `pip install` fails on mediapipe | Check `python3 --version` is 3.9-3.12. |
| Download timeouts | See the slow-internet instructions above. |

## Ideas for improvement

- Gesture recognition (fist, peace sign, thumbs up) mapped to LED patterns
- Servo or PWM LED controlled by how far a finger is bent
- Two-hand support (10 outputs with a shift register)
- Replace the bitmask with a small framed protocol for more devices

## Tech stack

Python, OpenCV, MediaPipe, PySerial, Arduino (C++)
