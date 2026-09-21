# Tests

```bash
python plugins/azure-deploy-kit/tests/run_tests.py        # summary
python plugins/azure-deploy-kit/tests/run_tests.py -v     # every assertion
```

Exit code is non-zero when anything fails. Requires PyYAML (`pip install pyyaml`) for the
template-parsing group; the rest is standard library.

## What is covered

| Group | Asserts |
|---|---|
| 1. Detector | `detect_stack.py` reports the right `existing_auth_method` for each fixture, and captures the publish-profile secret **name** |
| 2. Validator | `validate_workflows.py` passes valid auth/target pairs and FAILS impossible ones |
| 3. Templates | every template parses as YAML, carries the auth blocks it should, and has balanced `{{#if}}` markers |
| 4. Safety | no inline credential values anywhere in templates or fixtures |
| 5. Template surface | raw templates fail only the known pre-pruning artifacts |
| 6. Report template | `DEPLOYMENT.template.md` covers all five reader questions, carries the disclaimer, warns against secret values |
| 7. Report linter | `validate_report.py` passes `examples/DEPLOYMENT.example.md` and catches all 12 defects in a deliberately broken report |
| 8. Real-world regressions | the seven bugs found by the Vilje team's actual workflows stay fixed |
| 9. Versions and auth docs | `webapps-deploy` pinned to v3, the releases-API trap documented, `startup-command` limitation recorded, BUILD-08 / CI-09 in the rubric |

## Fixtures

Each is a minimal Node repo with one workflow in `.github/workflows/deploy.yml`.

| Fixture | Represents | Expected |
|---|---|---|
| `publish-profile-app-service` | **the Vilje team pattern** | passes |
| `oidc-app-service` | OIDC federated credentials | passes |
| `sp-secret-app-service` | service principal secret | passes |
| `bad-publish-profile-container-apps` | publish profile on Container Apps | FAIL `auth-target-compatible` |
| `bad-publish-profile-static-web-apps` | publish profile on Static Web Apps | FAIL `auth-target-compatible` |
| `bad-publish-profile-az-cli` | publish profile plus an `az ...` step | FAIL `publish-profile-az-cli` |
| `bad-oidc-missing-id-token` | OIDC without `id-token: write` | FAIL `oidc-id-token` |
| `bad-id-token-unused` | `id-token: write` granted but unused | FAIL `id-token-unused` |
| `team-publish-profile-monorepo` | **the real Vilje backend + frontend pair**, verbatim | detector reads workflow `env:` pins, `vars.*`, app names and the documented `npm install`; validator raises `multi-deploy-paths-filter` |

Fixtures contain **no real credentials** — only `${{ secrets.NAME }}` references. Group 4
enforces that, so a fixture with a pasted secret fails the suite.

## Adding a case

1. Add a fixture directory with `.github/workflows/deploy.yml` and a `package.json`.
2. Add a row to `CASES` in `run_tests.py`: the auth method the detector must report, the
   check IDs that must fail, and the check IDs that must pass.
3. Run the suite. A new check that nothing asserts is a check nobody is protecting.

## What these tests do not prove

They verify structure and logic only. **No generated workflow has been run against real
Azure.** Passing this suite does not mean a deployment will succeed — it means the YAML is
well-formed and the auth/target combination is not impossible.
