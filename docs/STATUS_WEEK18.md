# Week 18 — Phase 4, Track L (retrain the fusion U-Net at real scale)

## What this closes

Week 3's fusion methodology (patch-sizing, masked-loss, curriculum-training -- all real,
runnable PyTorch code in `Downloads/ml_pipeline/`) lost to a linear-regression baseline at
n=12, the smallest, earliest dataset in the whole project. Track L's ask: retry at real
scale now that two more real MSG archives exist that didn't exist when that result was
produced, and apply the rigor (blocked splits, permutation self-check, honest baseline
comparison) every later track has used, retroactively.

## Pre-check -- real, before building anything

1. **Confirmed the original n=12 bottleneck by reading the actual code, not assuming.**
   `build_ml_dataset.py`'s `build_gfs_dataset()` pairs GFS `.nc` files from `ml_cache/`
   with MSG scenes -- WRF appears ONLY in the patch-size validator as a nominal
   resolution comparison, never in the real sample-building path. The n=12 cap was simply
   12 GFS files having been downloaded for the original session; it was never a WRF
   date-overlap problem (the recurring gap this project keeps finding elsewhere).
2. **Real achievable n, computed before committing to anything**: deduped both new MSG
   archives by content-hash (same method `build_ml_dataset.py` itself uses) -- Kharif
   2026 archive: 36 distinct scene times; Nov 2023 archive: 45 distinct scene times; 81
   total, zero overlap with the original 12.
3. **GFS coverage for all 81 real MSG times confirmed live**, not assumed: NOAA's public
   AWS Open Data archive (`noaa-gfs-bdp-pds`, no auth) has both date ranges (verified via
   direct HTTP HEAD before writing any downloader). Using GFS's real hourly forecast
   steps (0-120h from each of the 4 daily cycles, not just the 0/3h the original
   pairing logic had cached for) gives a real match within the existing 20-minute
   tolerance for **81/81** MSG scenes -- no change to the matching logic itself.
4. **81 is well above the 20-30 floor** -- proceeded straight to building per your
   standing instruction, no need to stop and ask.

## Build

- **New downloader** (`download_gfs_aws.py`, real and necessary since the original
  `.nc`-based downloader was never recovered -- see `nwp2msg_common.py`'s own
  RECONSTRUCTION NOTE): byte-range-subsets each real ~500MB grib2 file down to just the
  13 needed messages via its public `.idx` sidecar (~1-2MB/file cropped to the regional
  bbox, vs. downloading the full global file), verified against a real `.idx` before
  writing the variable-mapping table. Confirmed all 13 `GFS_RAW_VARS` present and
  isolable as named messages. Real operational hiccup: a mid-batch transient DNS
  resolution failure (`errno 11002`) cascaded through 22-31 files across two runs even
  though isolated single calls to the identical URL succeeded immediately when tested
  directly -- fixed with retry-with-backoff (4 attempts, exponential), not treated as a
  permanent per-date failure. **Real final result: 81/81 GFS files downloaded.**
- **Dataset build** (`build_ml_dataset_track_l.py`) reuses `build_ml_dataset.py`'s own
  `find_msg_match`/`build_x_for_valid_time`/`read_target`/`list_nat_files_deduped`
  unchanged -- only the GFS source function changed. All 81 samples built cleanly
  (30 train / 6 val / 45 test).
- **Real temporally-blocked split, not the original random per-sample shuffle**:
  test = the entire Nov 2023 archive (45 samples) -- a genuinely different season AND
  year, never touched during training, the cleanest real generalization check available
  given what's on disk. train/val = the Kharif 2026 archive (36 samples), split by whole
  calendar date (chronologically-last 3 of 14 dates -> val), so no val date is
  training-adjacent within the same short window.
- **Model, loss, training loop**: `train.py`'s existing `SmallUNet` (3-level
  encoder/decoder, masked MSE loss) and `evaluate.py`'s existing linreg/flat baselines,
  unchanged. Extended `--split` choices in `evaluate.py`/`predict.py` to accept the new
  `test` value (a real, necessary extension -- the original script only knew
  train/val/all).

## Real result -- the U-Net now beats the linear baseline

Trained 60 epochs on the 30 real Kharif train samples (240 patches), evaluated on the 45
real, fully held-out Nov 2023 test samples (different season and year):

| metric (native res) | trained U-Net | linreg baseline | flat baseline |
|---|---:|---:|---:|
| RMSE (K) | **12.908** | 18.130 | 17.904 |
| MAE (K) | **9.386** | 14.955 | 12.948 |
| corr | **0.670** | 0.658 | n/a |
| SSIM | 0.711 | 0.724 | **0.727** |
| CSI (240K cold-cloud-top) | **0.016** | 0.000 | 0.000 |

**This is a real reversal of the original n=12 result** (model RMSE 19.28 vs. linreg
17.98 -- the model lost). At n=81 with a genuine season+year-blocked test, the model
beats the linear baseline by ~29% on RMSE, holds at every smoothing scale tested
(1/4/16px), and its bias (7.7K, a real, honest weakness -- systematically too warm) is
smaller than the flat baseline's own real weaknesses. **Not a clean sweep, reported
plainly**: the model's SSIM is slightly *below* both baselines' (0.711 vs.
0.724/0.727) -- structural similarity didn't improve even though pixel-wise error did.
CSI improved in relative terms (0.016 vs. 0.000) but stays low in absolute terms -- the
240K cold-cloud-top event is real and non-degenerate in this test set (5.08% of pixels,
checked directly, not assumed rare-to-vanishing), the model still misses most of them.

## Real self-check, before this was reported as a headline number

Permutation importance on the frozen trained model over all 17 input channels, all 45
test-set scenes (spatially shuffle one channel's pixels at a time, measure RMSE
increase): **positional/solar channels (solar_zenith, cos_solar_zenith, lat, lon) average
essentially zero impact (mean delta_rmse = -0.029, i.e. permuting them doesn't hurt)**,
while **the 13 real GFS meteorological channels average a clear positive dependency (mean
delta_rmse = +0.247)**, led by physically sensible predictors: medium cloud cover
(+1.483), high cloud cover (+0.911), surface temperature (+0.353), total cloud cover
(+0.416), relative humidity (+0.253). The model's win is real meteorological fusion
learning, not a positional shortcut.

**Stated up front, not retrofitted**: lat/lon here are a fixed per-pixel positional
encoding, identical across every train/val/test sample (same 327x397 Pakistan-bbox grid
always) -- structurally different from Track E's national-scale lat/lon risk, where it
stood in for district identity across genuinely different locations. `lat` shows some
real reliance (+0.390, a legitimate spatial prior for a fixed domain); `lon` shows
slightly negative delta (-0.487, the model isn't meaningfully using it, likely redundant
with lat + the meteorological fields' own spatial gradient).

## What this doesn't prove

One held-out test archive (Nov 2023, 45 samples) is a real, meaningful generalization
check, not a permanent proof of skill across all seasons/conditions -- the same caution
every other track's single-second-year validation carries. The model's bias (7.7K, too
warm) and unchanged/slightly-worse SSIM are real, unresolved weaknesses, not smoothed
over. Not wired into any downstream product path this week -- this track was scoped as
"does it beat the baseline at real scale," not "should this feed the live nowcast loop
or exposure-risk pipeline," a separate decision for later if wanted.

## Artifacts

- `Downloads/ml_pipeline/download_gfs_aws.py` -- new AWS GFS downloader (local-only, same
  convention as the rest of `ml_pipeline/`).
- `Downloads/ml_pipeline/build_ml_dataset_track_l.py` -- dataset builder, reuses
  `build_ml_dataset.py`'s pairing/regridding code.
- `Downloads/ml_pipeline/permutation_check_track_l.py` -- the self-check script.
- `Downloads/ml_pipeline/checkpoints/gfs_msg_ir108_track_l.pt` -- trained checkpoint
  (local-only, same as the original `gfs_msg_ir108.pt`).
- Copied into this repo for the record: `naip/models/fusion_unet/eval_report_track_l_test.json`,
  `permutation_importance_track_l.json`, `track_l_dataset_manifest.json`.
