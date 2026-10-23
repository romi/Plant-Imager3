# Camera tuning

Reference for the RPCCamera controls: locked defaults, advertised ranges, and the gotchas found while tuning them. Source values come from the picamera1 hardware dump (IMX477, 27 controls) and the test1/test2 rig frames.

## Locked defaults

`Camera.DEFAULT_CONTROLS` — applied at boot when no persisted file exists, and restored by `reset_controls(factory=True)`:

| Control | Value | Why |
|---|---|---|
| `AeEnable` | `False` | Fixed rig + daylight LEDs; black background fools auto-exposure |
| `ExposureTime` | `250000` µs | test2 winner (`--shutter 250ms`); the 15000 µs placeholder was ~70x underexposed at Lux ~5.4 |
| `AnalogueGain` | `7.0` | test2 winner (`--gain 7`); auto's 16x was visibly noisy |
| `AwbEnable` | `False` | Locked WB; driver default is `None` (unset), so this must be explicit |
| `AwbMode` | `5` (daylight) | Preset matching the rig lighting; see name table below |
| `ColourGains` | `(3.215, 1.433)` | test2 readback; red far above the (1.8, 1.4) guess, which would cast green |
| `AeMeteringMode` | `1` (Spot) | Harmless locked; auto is off anyway |
| `Brightness` | `0.0` | Neutral ISP |
| `Contrast` / `Saturation` | `1.0` | Neutral ISP |
| `Sharpness` | `1.0` | Neutral ISP |

Read back what's live via the `config` property; every scan image also carries the effective values as metadata (`ExposureTime`, `AnalogueGain`, `ColourGains`, `FrameDuration`, `Lux`, `ColourTemperature`).

## Advertised controls and ranges

`get_camera_controls()` returns this set as JSON (`bool` / `scalar` / `enum` / `tuple` schemas). `FrameRate` is **not** among them — it is virtual (accepted by the `config` setter for the video configuration, omitted from ranges).

| Control | Locked | Range | Notes |
|---|---|---|---|
| `AeEnable` | `False` | bool | |
| `AeConstraintMode` | – | 0 – 3 (enum) | inert while `AeEnable` is False |
| `AeExposureMode` | – | 0 – 3 (enum) | inert while `AeEnable` is False |
| `AeMeteringMode` | `1` | 0 – 3 (enum) | 0 CentreWeighted, 1 Spot, 2 Matrix, 3 Custom |
| `AeFlickerMode` | – | 0 – 1 (enum) | only relevant with flicker avoidance |
| `AeFlickerPeriod` | – | 100 – 1000000 µs (driver default `None`) | only relevant with flicker avoidance |
| `ExposureTime` | `250000` | 74 – 694422939 µs, `0` = auto | main brightness knob |
| `ExposureTimeMode` | – | 0 – 1 (enum: Auto/Manual) | |
| `ExposureValue` | – | −8.0 – +8.0 EV | inert while `AeEnable` is False |
| `AnalogueGain` | `7.0` | 1.0 – 22.26, `0` = auto | requested vs actual is quantized (asked 7 → 6.966) |
| `AnalogueGainMode` | – | 0 – 1 (enum: Auto/Manual) | |
| `AwbEnable` | `False` | bool (driver default `None`) | |
| `AwbMode` | `5` | 0 – 7 (enum) | see name table below |
| `ColourGains` | `(3.215, 1.433)` | 2-tuple (R, B), each 0.0 – 32.0 | never `(0, 0)` (see gotchas) |
| `ColourTemperature` | readback only | 100 – 100000 K | logged per image; test2 read 6669 K |
| `ColourCorrectionMatrix` | – | 3x3, each 0.0 – 8.0 | future calibration lever |
| `Brightness` | `0.0` | −1.0 – 1.0 | leave alone |
| `Contrast` | `1.0` | 0.0 – 32.0 | leave alone |
| `Saturation` | `1.0` | 0.0 – 32.0 | leave alone |
| `Sharpness` | `1.0` | 0.0 – 16.0 | leave alone |
| `NoiseReductionMode` | – | 0 – 4 (enum) | available if denoising is needed |
| `HdrMode` | – | 0 – 4 (enum) | available for high-dynamic-range scenes |
| `ScalerCrop` | – | rectangle tuple, (0,0,64,64) – (0,0,4056,3040) | active area starts at (8, 16) |
| `FrameDurationLimits` | – | 2-tuple, up to ~694 s | video-config `FrameRate` overrides the default ~30 fps |
| `SyncFrames` / `SyncMode` | – | 1 – 1000000 / 0 – 2 | hardware sync; not needed single-camera |
| `CnnEnableInputTensor` | – | bool | not needed for plant imaging |
| `StatsOutputEnable` | – | bool | not needed for plant imaging |

### AwbMode values and names

Per libcamera (`control_ids_core.yaml`); `5` confirmed against the rig:

| Value | Name |
|---|---|
| 0 | Auto |
| 1 | Incandescent |
| 2 | Tungsten |
| 3 | Fluorescent |
| 4 | Indoor |
| 5 | Daylight |
| 6 | Cloudy |
| 7 | Custom |

## Gotchas

- **`ColourGains: (0, 0)` silently re-enables AWB.** Accepted without error, then white balance drifts. The validator rejects it; never write it by hand.
- **`ExposureTime` / `AnalogueGain` of `0` mean auto**, not "off". Below their minima but legal sentinels.
- **`FrameRate` is virtual.** Settable (video path needs it), never advertised — don't expect it in ranges or metadata.
- **Gain is quantized.** What you request is approximate; compare readbacks with tolerance, never exact equality.
- **Out-of-range values hang the camera.** picamera2 accepts anything; a ~27-hour exposure blocked `capture_metadata()` forever on the rig. Per-key validation is mandatory, not optional — don't bypass the setter.
- **Only Appendix C names survive.** Since validation, the scanner's per-camera `config` push rejects unknown keys instead of silently applying nothing. A scan failing right after this change means a stale key in the scan config, not a broken camera.

## General tuning guidelines

- **Expose with shutter before gain.** The plant doesn't move; test1 at gain 16 was all noise in the blacks, test2 at 250 ms / 7x is clean. If scans get too slow, add light, not gain.
- **Judge on plant pixels and the Voronoi patches, not the background.** Lifted gray blacks are fine; clipped plant highlights are not.
- **Change one variable at a time** and check `Lux` / `ColourTemperature` readback alongside the image — stable `Lux` + drifting brightness means your change did it; drifting `Lux` means the rig lighting did.
- **Persist deliberately.** Session `config` writes are live-only; only `set_default_controls` writes the file. Verify with a `reset_controls` round-trip before calling a session done.
- **Leave the neutral ISP alone** (`Brightness`/`Contrast`/`Saturation`/`Sharpness`) unless you have a reason stated in the session log — color work belongs in post-processing against the in-scene patches.
