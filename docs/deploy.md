# Deploying What If FC to Azure Container Apps

**Live URL**: https://whatif-fc.politehill-9f24cffd.centralindia.azurecontainerapps.io

Fixed resource names used throughout:

| Resource | Name |
|----------|------|
| Resource group | `rg-pl-hackathon` |
| Location | `centralindia` |
| Container Apps environment | `whatif-env` |
| Container App | `whatif-fc` |
| Managed identity | `id-whatif-api` |
| Storage account | `whatifreplay` |
| Blob container | `replay` |
| KQL database | `whatif` |

> **Git Bash on Windows**: prefix `az` commands with `MSYS_NO_PATHCONV=1` to stop
> Bash converting `https://...` paths to Windows file paths.
>
> **Reading values from .env**:
> ```bash
> grep "^KEY=" .env | tail -1 | cut -d= -f2- | tr -d '\r'
> ```

---

## Prerequisites

- Azure CLI ≥ 2.57 with `containerapp` extension:
  `az extension add --name containerapp`

---

## 1 — Load config from .env

Run this once per shell session before the `az` commands below:

```bash
KQL_CLUSTER_URI=$(grep "^KQL_CLUSTER_URI=" .env | tail -1 | cut -d= -f2- | tr -d '\r')
FOUNDRY_PROJECT_ENDPOINT=$(grep "^FOUNDRY_PROJECT_ENDPOINT=" .env | tail -1 | cut -d= -f2- | tr -d '\r')
FOUNDRY_MODEL=$(grep "^FOUNDRY_MODEL=" .env | tail -1 | cut -d= -f2- | tr -d '\r')
REPLAY_STORAGE_ACCOUNT_URL=$(grep "^REPLAY_STORAGE_ACCOUNT_URL=" .env | tail -1 | cut -d= -f2- | tr -d '\r')
```

---

## 2 — One-time infrastructure setup

### Resource group and Container Apps environment

```bash
az group create \
  --name rg-pl-hackathon \
  --location centralindia

az containerapp env create \
  --name whatif-env \
  --resource-group rg-pl-hackathon \
  --location centralindia
```

### User-assigned managed identity

```bash
az identity create \
  --name id-whatif-api \
  --resource-group rg-pl-hackathon \
  --location centralindia

IDENTITY_CLIENT_ID=$(az identity show \
  --name id-whatif-api \
  --resource-group rg-pl-hackathon \
  --query clientId -o tsv)

IDENTITY_RESOURCE_ID=$(az identity show \
  --name id-whatif-api \
  --resource-group rg-pl-hackathon \
  --query id -o tsv)
```

Grant the identity read access to the replay storage account:

```bash
STORAGE_SCOPE=$(az storage account show \
  --name whatifreplay \
  --resource-group rg-pl-hackathon \
  --query id -o tsv)

az role assignment create \
  --assignee "$IDENTITY_CLIENT_ID" \
  --role "Storage Blob Data Reader" \
  --scope "$STORAGE_SCOPE"
```

---

## 3 — Create the Container App

```bash
az containerapp create \
  --name whatif-fc \
  --resource-group rg-pl-hackathon \
  --environment whatif-env \
  --image ghcr.io/aravindh-c/what-if-fc:latest \
  --ingress external \
  --target-port 8000 \
  --min-replicas 1 \
  --max-replicas 1 \
  --user-assigned "$IDENTITY_RESOURCE_ID" \
  --env-vars \
    AZURE_CLIENT_ID="$IDENTITY_CLIENT_ID" \
    REPLAY_STORAGE_ACCOUNT_URL="$REPLAY_STORAGE_ACCOUNT_URL" \
    REPLAY_CONTAINER="replay" \
    KQL_CLUSTER_URI="$KQL_CLUSTER_URI" \
    KQL_DATABASE="whatif" \
    FOUNDRY_PROJECT_ENDPOINT="$FOUNDRY_PROJECT_ENDPOINT" \
    FOUNDRY_MODEL="$FOUNDRY_MODEL"
```

The image sets `WHATIF_MODE=replay` by default. Live mode activates automatically when
`KQL_CLUSTER_URI` and `KQL_DATABASE` are present.

---

## 4 — Subsequent deploys

CI pushes a new image and runs `az containerapp update` automatically on every merge
to `main` (once the OIDC secrets are configured — see section 5).

To deploy manually:

```bash
az containerapp update \
  --name whatif-fc \
  --resource-group rg-pl-hackathon \
  --image ghcr.io/aravindh-c/what-if-fc:<git-sha>
```

---

## 5 — OIDC federated credential for GitHub Actions

The CI deploy job uses `azure/login@v2` with OIDC and a **user-assigned managed
identity** (`id-whatif-deploy`). No App Registration or service principal is needed.

> **Critical — OIDC subject format**: GitHub's token for this repository uses numeric
> owner and repository IDs in the subject claim, not the plain `owner/repo` slug.
> The classic subject `repo:aravindh-c/what-if-fc:ref:refs/heads/main` fails with
> **AADSTS700213**. Use the ID-based subject instead:
>
> ```
> repo:aravindh-c@61825537/what-if-fc@1423213635:ref:refs/heads/main
> ```
>
> (61825537 = GitHub user ID for aravindh-c; 1423213635 = repository ID for what-if-fc)

### 5a — Create the deployment identity

```bash
az identity create \
  --name id-whatif-deploy \
  --resource-group rg-pl-hackathon \
  --location centralindia

DEPLOY_CLIENT_ID=$(az identity show \
  --name id-whatif-deploy \
  --resource-group rg-pl-hackathon \
  --query clientId -o tsv)
```

### 5b — Grant Contributor on the resource group

```bash
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

az role assignment create \
  --assignee "$DEPLOY_CLIENT_ID" \
  --role Contributor \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/rg-pl-hackathon"
```

### 5c — Add a federated credential for the main branch

```bash
az identity federated-credential create \
  --name github-actions-main \
  --identity-name id-whatif-deploy \
  --resource-group rg-pl-hackathon \
  --issuer "https://token.actions.githubusercontent.com" \
  --subject "repo:aravindh-c@61825537/what-if-fc@1423213635:ref:refs/heads/main" \
  --audiences "api://AzureADTokenExchange"
```

### 5d — Add GitHub repository secrets

In **Settings → Secrets and variables → Actions**, add:

| Secret | Value |
|--------|-------|
| `AZURE_CLIENT_ID` | `$DEPLOY_CLIENT_ID` (client ID of `id-whatif-deploy`) |
| `AZURE_TENANT_ID` | `az account show --query tenantId -o tsv` |
| `AZURE_SUBSCRIPTION_ID` | `az account show --query id -o tsv` |

Once these three secrets are set the CI deploy job activates automatically on the next
push to `main`.

---

## Environment variable reference

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_CLIENT_ID` | Yes (Azure) | Client ID of `id-whatif-api` managed identity |
| `REPLAY_STORAGE_ACCOUNT_URL` | Replay mode | `https://whatifreplay.blob.core.windows.net` |
| `REPLAY_CONTAINER` | Replay mode | `replay` |
| `KQL_CLUSTER_URI` | Live mode | From `.env` — `KQL_CLUSTER_URI` |
| `KQL_DATABASE` | Live mode | `whatif` |
| `FOUNDRY_PROJECT_ENDPOINT` | Live mode | From `.env` — `FOUNDRY_PROJECT_ENDPOINT` |
| `FOUNDRY_MODEL` | Live mode | From `.env` — `FOUNDRY_MODEL` |
| `WHATIF_MODE` | No | `replay` (default, set in image) |
