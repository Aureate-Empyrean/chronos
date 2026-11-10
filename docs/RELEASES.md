# Chronos releases and provenance

## Version control history

Development from 0.1.1 (commit `9b6ac7a`) to 0.4.0 was not committed as it happened. Intermediate versions have no history and none was reconstructed. Commits and tags carry their true creation date, which is after deployment.

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

## Rewritten commit identifiers

This repository's history was rewritten on 2026-11-10. Earlier entries keep the identifiers recorded at the time. The tables give the current ones.

| Old commit | New commit |
| --- | --- |
| `89cafddb54` | `4b16427653` |
| `d1183919a9` | `7bc245c245` |
| `7b2d16531e` | `475ef1414f` |
| `0ebb2d1ea8` | `5d8a033f6d` |
| `8eabe463cd` | `460b518c3f` |

| Tag | Old object | New object |
| --- | --- | --- |
| `v0.4.0` | `d611ee9620` | `1291f7d446` |
| `v0.5.0` | `08876d1671` | `b9fd33bd2d` |
