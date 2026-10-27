"""
hand_leds.py - Control 5 Arduino LEDs with your fingers, in real time.

Pipeline:
  laptop camera (OpenCV) -> hand landmarks (MediaPipe) -> open/closed per finger
  -> smoothing -> 1 byte over serial -> Arduino -> LEDs

Usage:
  python hand_leds.py                    # auto-detect Arduino port
  python hand_leds.py --port COM3        # Windows
  python hand_leds.py --port /dev/ttyACM0
  python hand_leds.py --no-serial        # test vision only, no Arduino
  python hand_leds.py --camera 1         # use another camera index

Press 'q' or ESC in the video window to quit.
"""

import argparse
import math
import sys
import time
from collections import deque

import cv2
import mediapipe as mp

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None

FINGER_NAMES = ["Thumb", "Index", "Middle", "Ring", "Pinky"]

# MediaPipe landmark ids
WRIST = 0
THUMB_IP, THUMB_TIP = 3, 4
PINKY_MCP = 17
# (pip, tip) for index, middle, ring, pinky
FINGER_JOINTS = [(6, 8), (10, 12), (14, 16), (18, 20)]

# Tuning
OPEN_RATIO = 1.05      # tip must be this much farther than the joint to count as "open"
SMOOTH_FRAMES = 5      # majority vote over the last N frames (kills flicker)
HEARTBEAT_S = 0.5      # resend state at least this often (Arduino failsafe needs it)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def find_arduino_port():
    if serial is None:
        return None
    keywords = ("arduino", "ch340", "ch341", "usb serial", "usb-serial", "ttyacm", "wch")
    for p in list_ports.comports():
        text = f"{p.description} {p.manufacturer} {p.device}".lower()
        if any(k in text for k in keywords):
            return p.device
    return None


def fingers_open(points):
    """
    points: list of 21 (x, y) pixel coords.
    Returns [thumb, index, middle, ring, pinky] as bools (True = open).

    Rotation-invariant: compares distances instead of 'tip is above joint',
    so it still works if your hand is tilted or sideways.
    """
    wrist = points[WRIST]
    states = []

    # Thumb: compare tip vs IP joint distance to the base of the pinky.
    # Open thumb sticks away from the palm; closed thumb tucks toward it.
    thumb_open = dist(points[THUMB_TIP], points[PINKY_MCP]) > OPEN_RATIO * dist(
        points[THUMB_IP], points[PINKY_MCP]
    )
    states.append(thumb_open)

    # Other fingers: tip farther from the wrist than the PIP joint = extended.
    for pip, tip in FINGER_JOINTS:
        states.append(dist(points[tip], wrist) > OPEN_RATIO * dist(points[pip], wrist))

    return states


def states_to_mask(states):
    mask = 0
    for i, is_open in enumerate(states):
        if is_open:
            mask |= 1 << i
    return mask


def draw_hud(frame, states, mask, connected):
    h, w = frame.shape[:2]
    for i, name in enumerate(FINGER_NAMES):
        is_open = states[i] if states else False
        color = (0, 220, 0) if is_open else (60, 60, 255)
        cv2.circle(frame, (30 + i * 90, h - 50), 14, color, -1)
        cv2.putText(frame, name, (10 + i * 90, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    status = f"mask={mask:05b}  serial={'ON' if connected else 'OFF'}"
    cv2.putText(frame, status, (10, 25), cv2.FONT_HERSHEY_SIMPLEX,
                0.6, (255, 255, 0), 2, cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="Serial port (e.g. COM3, /dev/ttyACM0)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--no-serial", action="store_true", help="vision only, no Arduino")
    ap.add_argument("--no-mirror", action="store_true", help="don't flip the preview")
    args = ap.parse_args()

    # ---- Serial ----
    ser = None
    if not args.no_serial:
        if serial is None:
            sys.exit("pyserial missing: pip install pyserial")
        port = args.port or find_arduino_port()
        if not port:
            sys.exit("No Arduino found. Plug it in, or pass --port, or use --no-serial.")
        try:
            ser = serial.Serial(port, args.baud, timeout=0)
        except serial.SerialException as e:
            sys.exit(f"Could not open {port}: {e}\n"
                     "Close the Arduino IDE Serial Monitor and try again.")
        print(f"Opened {port} @ {args.baud}")
        time.sleep(2.0)  # Uno resets when the port opens; wait for it to boot

    # ---- Camera ----
    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        sys.exit(f"Cannot open camera {args.camera}")

    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils
    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        model_complexity=0,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.5,
    )

    history = deque(maxlen=SMOOTH_FRAMES)
    last_sent_mask = None
    last_sent_time = 0.0
    prev_t = time.time()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera read failed")
                break
            if not args.no_mirror:
                frame = cv2.flip(frame, 1)

            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = hands.process(rgb)

            if result.multi_hand_landmarks:
                lm = result.multi_hand_landmarks[0]
                pts = [(p.x * w, p.y * h) for p in lm.landmark]
                history.append(fingers_open(pts))
                mp_draw.draw_landmarks(frame, lm, mp_hands.HAND_CONNECTIONS)
            else:
                history.clear()  # no hand -> all LEDs off

            # Majority vote across recent frames
            if history:
                smooth = [
                    sum(f[i] for f in history) > len(history) / 2 for i in range(5)
                ]
            else:
                smooth = [False] * 5
            mask = states_to_mask(smooth)

            # Send on change, plus a heartbeat
            now = time.time()
            if ser and (mask != last_sent_mask or now - last_sent_time > HEARTBEAT_S):
                try:
                    ser.write(bytes([mask]))
                except serial.SerialException:
                    print("Serial connection lost")
                    break
                last_sent_mask, last_sent_time = mask, now

            fps = 1.0 / max(now - prev_t, 1e-6)
            prev_t = now
            cv2.putText(frame, f"{fps:.0f} FPS", (w - 90, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
            draw_hud(frame, smooth, mask, ser is not None)
            cv2.imshow("Hand -> LEDs", frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    finally:
        if ser:
            try:
                ser.write(bytes([0]))  # LEDs off
                ser.close()
            except Exception:
                pass
        cap.release()
        hands.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()