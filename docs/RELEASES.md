# Chronos releases and provenance

## Version control history

Development from 0.1.1 (commit `9b6ac7a`) to 0.4.0 was not committed as it happened. Intermediate versions have no history and none was reconstructed. Commits and tags carry their true creation date, which is after deployment.

## 0.5.0

| | |
| --- | --- |
| Tag | `v0.5.0` (annotated, tag object `08876d16714a3e46d7cab1d2b49b160085c5d8a0`) |
| Release commit | `7b2d16531ed12c1dd01c47ff54dcb7a06077d517`, created 2026-11-09 before any deployment |
| Release image | `sha256:6049980fec6047aed99c64721f5d475023660d397fb7c87a6f6ec0e097d1f14b`, built from a clean clone of this commit |
| Image built | 2026-11-09T18:14:58.672301687Z |
| Deployed | **Not deployed to Exodus.** This image runs on aetest |
| CI | This repository has no GitHub Actions workflow. The equivalent checks ran locally from a clean clone |

### What has been demonstrated

Checked on 2026-11-09. Evidence is in `VALIDATION_P1_NAVIGATION_AETEST_2026-11-09.md` at the workspace root.

- All 20 files under the image's `/app/backend` and `/app/frontend` are byte-identical to this commit.
- Against the working-tree build first validated on aetest, those files match except for line endings: 7 byte-identical and 13 differing only in line endings.
- This exact image was then installed on aetest, and the universal navigation journeys passed against it in Chromium, WebKit and Firefox on Linux.
- The unit suite passes on the clean clone: 33 passed.

### What has not been demonstrated

- The build is **not reproducible to the digest**. Rebuilds of unchanged source gave different image IDs.
- Physical mouse buttons, native keyboard shortcuts, Safari and real phones have not been checked.
- It has not run in production.

## 0.4.0

| | |
| --- | --- |
| Tag | `v0.4.0` (annotated, tag object `d611ee962087b9f92cc93650d1496fb41ea54a5c`) |
| Baseline commit | `89cafddb54b4ee549aadbaf523c063221c6b7dcb`, created 2026-11-09 after deployment |
| Deployed image | `sha256:8b2e88a6c091742ba5a1a85b8bc701f1cdf331015c328182029c7cd12f2671b6` |
| Image config | `sha256:f4e03642886fa8a280454a83542bafcd140f93b6e39b46d6902f455dff51ea11` |
| Image built | 2026-11-09T08:43:36.719394882Z |
| Deployed | Exodus, 2026-11-09. The running container's image was read back on 2026-11-09 and matches the digest above |

### What has been demonstrated

Checked on 2026-11-09 from a clean clone of the tagged commit, against the image archive saved at release time.

- Of 20 non-compiled files in the image's `/app`, 5 are byte-identical to the tag and 15 differ only in line endings.
- The image was rebuilt with `deploy/Dockerfile`. Every file outside `/app` that is not a compiled `.pyc` is identical. Entrypoint, environment and user are the same.
- The unit suite passes on the clone: 33 passed.

### What has not been demonstrated

The build is **not reproducible to the digest**. Two rebuilds gave two different digests, sharing 5 of 11 layers with the deployed image.

- The deployed image was built from a Windows working tree, so 15 text files have CRLF line endings there and LF here.
- The deployed image holds 9 extra `.pyc` files under `/app`, copied from local test runs because `.dockerignore` does not exclude `__pycache__`. A clean checkout has none.
- 687 `.pyc` files from installed packages differ between builds, because they embed build-time data.
- The commit was made after the image was built. It records matching content, not the build's actual input.

## Conventions

Create the tag before deploying and build from a clean checkout of it. Record the commit and image digest in the deployment record. Do not move a published tag.
