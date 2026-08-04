# KMC analog scale-read — labeled validation set

Ground-truth labels for calibrating the scale-read validator on **analog dial** scales.
Grounded from the raw KMC visit exports; one row per follow-up visit that has a weight
photo **and** a typed weight.

## Files
- `kmc_analog_scale_labels.csv` — 1,766 labeled rows across EHA + BERI + NAMA V3.

## Projects / scale types
| opp | project | scale (analog) |
|---|---|---|
| 1236 | EHA | UNICEF **Salter 235 6S** hanging dial — 25 kg × 100 g |
| 1790 | BERI | UNICEF **Salter 235 6S** hanging dial — 25 kg × 100 g (same design as EHA) |
| 1488 | NAMA V3 | **KINLee** flat-bed/round dial — 20 kg × 100 g (a *visually different* dial) |

Both dial designs are included on purpose — the Salter (hanging, round face) and the
KINLee (flat-bed, small window) look quite different and should both be covered.

## Columns
| column | meaning |
|---|---|
| `opp_id`, `project`, `scale_type` | which project + physical scale |
| `submission_id` | Connect visit/submission id — join key to pull the image |
| `instance_id` | form `meta.instanceID` — alternate join key |
| `visit_date`, `flw_username` | context |
| `typed_weight_g` | **ground truth**: grams the FLW typed (`form.anthropometric.child_weight_visit`). The image is at `form.anthropometric.upload_weight_image`. |
| `plausible_300_6000` | `Y` if the typed value is in a plausible infant range (0.3–6.0 kg) |
| `gross_error_true_positive` | `Y` = typed value is **impossible** (e.g. 26000 g) → a confirmed read/entry error, i.e. a real **True Positive** for the classifier to catch |
| `note` | e.g. flags the one NAMA FLW who uses a **digital** handheld (exclude for a pure-analog set) |

## How to use
- **Match cases:** for correctly-recorded visits the typed value equals the dial, so
  `typed_weight_g` is the label the classifier should agree with (within ~100 g dial tolerance).
- **True-Positive seeds:** `gross_error_true_positive = Y` rows are unambiguous mismatches
  (implausible typed values) — good positive cases. Counts: **EHA 16, BERI 2, NAMA 0**.
- **Subtle mismatches** (typed ≠ dial but both in-range, e.g. typed 1500 g vs a dial at ~1600 g)
  are **not** flaggable from data alone — those are exactly what the calibrated read should catch,
  so they're the real precision test. Happy to help hand-label a subset from the images if useful.
- **Images:** join `submission_id` / `instance_id` to a `user_visits?images=true` pull (or the
  blob store) to get each photo. (We didn't embed blobs here; you have data access to pull them.)

## Notes
- The scale type is **not** recorded anywhere in the form — it's a per-project procurement fact
  (above), and not 100% enforced (one NAMA FLW uses digital). Auto-detecting dial-vs-LCD from the
  image is the safest signal.
- `typed_weight_g` is the FLW's entry; a mismatch to the dial means an FLW typo or fabrication —
  which is the thing the validator is meant to surface.
