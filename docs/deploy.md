# Deploying What If FC to Azure Container Apps

## Prerequisites

- Azure CLI ≥ 2.57 with `containerapp` extension  
  `az extension add --name containerapp`
- A GitHub Personal Access Token with `write:packages` scope **or** use the GITHUB_TOKEN
  secret wired up in CI (the CI workflow handles image publishing automatically).

---

## 1 — One-time infrastructure setup

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

# Capture the client ID — needed as AZURE_CLIENT_ID env var inside the container
IDENTITY_CLIENT_ID=$(az identity show \
  --name id-whatif-api \
  --resource-group rg-pl-hackathon \
  --query clientId -o tsv)

IDENTITY_RESOURCE_ID=$(az identity show \
  --name id-whatif-api \
  --resource-group rg-pl-hackathon \
  --query id -o tsv)
```

Grant the identity access to your Azure Blob storage account (for replay bundles):

```bash
STORAGE_SCOPE=$(az storage account show \
  --name <your-storage-account> \
  --resource-group rg-pl-hackathon \
  --query id -o tsv)

az role assignment create \
  --assignee "$IDENTITY_CLIENT_ID" \
  --role "Storage Blob Data Reader" \
  --scope "$STORAGE_SCOPE"
```

---

## 2 — Create the Container App

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
    REPLAY_STORAGE_ACCOUNT_URL="https://<your-storage-account>.blob.core.windows.net" \
    REPLAY_CONTAINER="replays" \
    KQL_CLUSTER_URI="https://<your-eventhouse>.<region>.kusto.fabric.microsoft.com" \
    KQL_DATABASE="EventHub" \
    FOUNDRY_PROJECT_ENDPOINT="https://<your-project>.api.azureml.ms" \
    FOUNDRY_MODEL="gpt-4o"
```

The app starts in `WHATIF_MODE=replay` by default (set in the image). The live-mode
endpoints activate automatically when `KQL_CLUSTER_URI` and `KQL_DATABASE` are set.

---

## 3 — Subsequent deploys

CI pushes a new image and updates the app automatically on every merge to `main`.
To deploy manually:

```bash
az containerapp update \
  --name whatif-fc \
  --resource-group rg-pl-hackathon \
  --image ghcr.io/aravindh-c/what-if-fc:<git-sha>
```

---

## 4 — OIDC federated credential for GitHub Actions

The CI deploy job logs in with OIDC (`azure/login@v2`). Set this up once:

### 4a — Create an App Registration (service principal)

```bash
az ad app create --display-name what-if-fc-ghactions
APP_ID=$(az ad app list --display-name what-if-fc-ghactions --query "[0].appId" -o tsv)

az ad sp create --id "$APP_ID"
SP_OBJECT_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)
```

### 4b — Grant Contributor on the resource group

```bash
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

az role assignment create \
  --assignee-object-id "$SP_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role Contributor \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/rg-pl-hackathon"
```

### 4c — Add a federated credential for the main branch

```bash
az ad app federated-credential create \
  --id "$APP_ID" \
  --parameters '{
    "name": "github-actions-main",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:aravindh-c/what-if-fc:ref:refs/heads/main",
    "description": "GitHub Actions OIDC – main branch",
    "audiences": ["api://AzureADTokenExchange"]
  }'
```

### 4d — Add GitHub repository secrets

In the GitHub repo → Settings → Secrets and variables → Actions, add:

| Secret | Value |
|--------|-------|
| `AZURE_CLIENT_ID` | `$APP_ID` (output from step 4a) |
| `AZURE_TENANT_ID` | `az account show --query tenantId -o tsv` |
| `AZURE_SUBSCRIPTION_ID` | `az account show --query id -o tsv` |

Once these three secrets are set, the CI deploy job activates automatically on the
next push to `main`.

---

## Environment variable reference

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_CLIENT_ID` | Yes (Azure) | Client ID of the user-assigned managed identity |
| `REPLAY_STORAGE_ACCOUNT_URL` | For replay mode | Blob storage account URL |
| `REPLAY_CONTAINER` | For replay mode | Container name holding replay JSON files |
| `KQL_CLUSTER_URI` | For live mode | Fabric EventHouse KQL cluster URI |
| `KQL_DATABASE` | For live mode | KQL database name |
| `FOUNDRY_PROJECT_ENDPOINT` | For live mode | Azure AI Foundry project endpoint |
| `FOUNDRY_MODEL` | For live mode | Model deployment name (e.g. `gpt-4o`) |
| `WHATIF_MODE` | No | `replay` (default, set in image) |
