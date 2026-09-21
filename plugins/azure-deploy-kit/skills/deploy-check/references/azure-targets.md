# Choosing the Azure target and the templates

## Recommend, then confirm

Never pick the target silently. Recommend one with a one-line reason drawn from the
detected facts, offer the alternatives, and let the user decide. If the user passed
`--target`, skip the question and use it.

## Decision table

| Detected shape | Recommend | Why |
|---|---|---|
| Static frontend only (React/Vite/Next static export/Angular/Vue), no server | **Static Web Apps** | Free tier, global CDN, no server to run |
| Frontend + a small API in the same repo | **Static Web Apps** (managed API) or **App Service** + separate SWA | SWA managed API suits light APIs; heavy ones need App Service |
| Single web service, no Dockerfile, standard runtime (Node/Python/.NET/Java) | **App Service (code)** | Simplest path; no registry needed |
| Single web service **with** a Dockerfile | **App Service (container)** or **Container Apps** | App Service if it is one always-on web app; Container Apps if you want scale-to-zero or revisions |
| Multiple containerized services, or needs scale-to-zero, revisions, or KEDA scaling | **Container Apps** | Built for it |
| Background worker / queue consumer, no HTTP | **Container Apps** (job or scale rule) | App Service expects HTTP and will restart a non-listening app |
| Event-driven functions (`host.json`, `function.json`, `@azure/functions`, `azure-functions`) | **Azure Functions** | Not templated in v0.1 — say so and stop rather than forcing a wrong target |
| Needs a specific VM, GPU, or arbitrary daemons | **AKS / VM** | Out of scope for v0.1 — say so |

When the recommendation is genuinely ambiguous, say so and present the trade-off in one
sentence each. Do not pretend to a certainty you do not have.

## Template selection

| Target | Deploy template | Pair with CI template |
|---|---|---|
| App Service, code deploy | `templates/deploy-app-service-code.yml` | matching `ci-*.yml` |
| App Service, container | `templates/deploy-app-service-container.yml` | matching `ci-*.yml` |
| Container Apps | `templates/deploy-container-apps.yml` | matching `ci-*.yml` |
| Static Web Apps | `templates/deploy-static-web-apps.yml` | `ci-node.yml` |

CI template by detected stack:

| Stack | CI template |
|---|---|
| Node / TypeScript (npm, pnpm, yarn) | `ci-node.yml` |
| Python (pip, poetry, uv) | `ci-python.yml` |
| .NET | `ci-dotnet.yml` |
| Anything else | Build from `ci-node.yml` as a shape reference, adapt the steps, and mark the result `Assumed` in the report |

### One workflow or two?

GitHub runs **every** file in `.github/workflows/`; it does not pick one. Each file's `on:`
block decides whether that file runs for a given event. So two files means two independent
triggers, and overlapping triggers mean duplicated work.

| Situation | Emit |
|---|---|
| Team wants checks on pull requests **and** deploy on merge | `ci.yml` (`on: pull_request`) **plus** `deploy.yml` (`on: push`) |
| Team just wants "push and it deploys" | **`deploy.yml` only** - the deploy workflow already builds and tests |
| Repo already has a single combined workflow | Keep that shape. Do not split it into two. |

Ask if it is not obvious. Defaulting to two files when the team wanted one adds a workflow
nobody asked for.

Never let both trigger on the same event (CI-10). The `ci-*.yml` templates are
`pull_request`-only for exactly this reason - the deploy workflow rebuilds on merge.

## Auth compatibility by target

Resolve this together with the target - an incompatible pair has to be caught before
generating, not after.

| Target | Allowed auth methods |
|---|---|
| App Service (code) | OIDC, service principal secret, publish profile |
| App Service (container) | OIDC, service principal secret, publish profile (see note) |
| Container Apps | OIDC, service principal secret |
| Static Web Apps | its own deployment token (`AZURE_STATIC_WEB_APPS_API_TOKEN`) |

Note: publish profile deploys the image fine, but gives no `az acr login`. Use GHCR, or
ACR with admin credentials.

Full detail and the reasoning in `auth.md`.

## Monorepos

If the detector reports more than one deployable service, resolve this **before**
generating anything. Ask which services to set up now, then for each chosen service:

- Give it its own workflow file, named `deploy-<service>.yml`, not one mega-workflow.
- Set `on.push.paths:` to that service's directory so an unrelated change does not
  trigger a needless deploy.
- Set a distinct `concurrency.group` per service.
- Set `working-directory:` (or the template's `{{APP_PATH}}`) to the service root.

Do not attempt a matrix over services with different stacks. Two clear workflows beat one
clever one.

## Ingress port by target

Values the generated config must agree with, and a frequent cause of a silent 502:

| Target | Port behaviour |
|---|---|
| App Service (code) | Injects `PORT`. The app must read it. |
| App Service (container) | Injects `WEBSITES_PORT` as an App Setting; it must equal the port the container listens on. |
| Container Apps | `--target-port` must equal the container's listening port. |
| Static Web Apps | No server port. |

## Out of scope for v0.1

Say plainly that these are not supported yet rather than improvising a template:
Azure Functions, AKS, Virtual Machines, Service Fabric, Bicep/Terraform provisioning.
Adding one means adding a tested template file plus a row in the tables above.
