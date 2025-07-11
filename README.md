# 🚀  flux-CouchDB
Learn to build, Dockerize, and deploy a Python Flask app on flux

# 📦 Project Setup
✅ Create Virtual Environment

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate


# ▶️ Build and Start the Stack
docker-compose up --build

# 🖥️ Access Services in Browser
Service	URL	Purpose
CouchDB	http://localhost:5984/_utils	Admin UI (user/pass: admin)
Dash App	http://localhost:8050	Car prices dashboard


# Multi platform
🌍 Build for Multi-Platform

docker buildx create --use

COMMIT_SHA=$(git rev-parse --short HEAD) && \
docker buildx build --platform linux/amd64,linux/arm64 \
  -t dockerelvis/car-dashboard:latest \
  -t dockerelvis/car-dashboard:$COMMIT_SHA \
  -f Dockerfile.app \
  --push .
echo $COMMIT_SHA

-----
COMMIT_SHA=$(git rev-parse --short HEAD) && \
docker buildx build --platform linux/amd64,linux/arm64 \
  -t dockerelvis/data-generator:latest \
  -t dockerelvis/data-generator:$COMMIT_SHA \
  -f Dockerfile.data \
  --push .
echo $COMMIT_SHA


# 🧩 Step 1: Install 
brew install fluxcd/tap/flux
flux --version


# 🧪 Start Minikube (3 Nodes)
minikube start --nodes 3 --cpus=2 --memory=4g
kubectl get nodes

# ⚙️ Access Nodes
minikube ssh --node=minikube
minikube ssh --node=minikube-m02
minikube ssh --node=minikube-m03

# ⛔ Taint and Label Nodes
kubectl taint nodes minikube node-role.kubernetes.io/master=:NoSchedule
kubectl label node minikube-m02 node-role.kubernetes.io/worker=""
kubectl label node minikube-m03 node-role.kubernetes.io/worker=""

# 🧹 Clean Minikube (if needed)
minikube stop minikube delete --all
minikube delete --all --purge

# 🧠 GitOps Explained
🛠️ What happens under the hood:
| Option                      | Meaning                                                                                                    |
| --------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `flux bootstrap github`     | Initializes GitOps with GitHub                                                                             |
| `--owner=Elvis-Ngwesse`     | GitHub username or org                                                                                     |
| `--repository=Flux-CouchDB` | GitHub repo name to push Flux config into                                                                  |
| `--branch=main`             | Branch to use (must exist)                                                                                 |
| `--path=./k8s`              | Local path in the repo where your Kubernetes YAMLs live (e.g., `kustomization.yaml`, `deployments/`, etc.) |


# 🚀 1. Deploy (Bootstrap & Add Resources)
Go to GitHub token settings and create a token with the necessary scopes:

"https://github.com/settings/tokens"
export GITHUB_TOKEN=ghp_xxx    # your personal GitHub token
flux bootstrap github \
  --owner=Elvis-Ngwesse \
  --repository=Flux-CouchDB \
  --branch=main \
  --path=./k8s \
  --personal


# ⬇️⬆️ 📥  git pull
Do a git pull since flux-system folder is created in remote

# 🔄 Force a manual reconciliation
flux reconcile kustomization couchdb --with-source
flux get all
flux get sources git
flux get kustomizations
kubectl get pods -n flux-system
flux check
kubectl -n flux-system delete pods --all
kubectl -n flux-system logs deployment/kustomize-controller -f
kubectl -n flux-system get kustomizations.kustomize.toolkit.fluxcd.io -o wide


# 🗑️ Clean Up Kubernetes Resources
kubectl delete namespace car-app
kubectl delete namespace car-logs

# 🌐 Minikube Port Forwards
| Service       | Namespace | Access Command                                 |
|---------------|-----------|------------------------------------------------|
| CouchDB       | car-app   | `minikube service couchdb-nodeport -n car-app` |
| Kibana        | car-logs  | `minikube service kibana -n car-logs`          |
| Car Dashboard | car-app   | `minikube service car-dashboard -n car-app`    |
| Elasticsearch | car-logs  | `minikube service elasticsearch -n car-logs`   |
| Chronograf    | car-logs  | `minikube service chronograf -n car-logs`      |
| cAdvisor      | car-logs  | `minikube service cadvisor -n car-logs`        |

# 🧪 Elasticsearch index check:
curl http://127.0.0.1:54306/_cat/indices?v

✅ Create a Data View in Kibana
Go to Kibana → Stack Management → Data Views
Click "Create data view"
Fill in:
Name: car-logs
Index pattern: k or F*
Optional: Set timestamp field (e.g., @timestamp)
Save and go to Discover to view logs.

# 📺 K9s: Terminal UI for Kubernetes
🧪 Install & Launch
brew install k9s
k9s
