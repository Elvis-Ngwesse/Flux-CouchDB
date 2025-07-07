# Openshift-CouchDB
Learn to build, Dockerize, and deploy a Python Flask app on OpenShift with CI/CD, using ConfigMaps, 
Secrets, and Routes—perfect for beginners mastering DevOps and cloud-native workflows.

# ✅ Create a Virtual Environment
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

🔁 Optional: Regenerate Data
To re-run only the data loader:

bash
Copy
Edit
docker-compose run --rm data-generator

🐳 Verify Running Containers
Check running containers:

bash
Copy
Edit
docker ps


# Multi platform
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


🧩 Step 1: Install 
brew install fluxcd/tap/flux
flux --version


minikube start --nodes 3
kubectl get nodes
minikube ssh --node=minikube
minikube ssh --node=minikube-m02
minikube ssh --node=minikube-m03

kubectl taint nodes minikube node-role.kubernetes.io/master=:NoSchedule

kubectl label node minikube-m02 node-role.kubernetes.io/worker=""
kubectl label node minikube-m03 node-role.kubernetes.io/worker=""


minikube stop minikube delete --all
minikube delete --all --purge

🌐 

flux bootstrap github \
  --owner=Elvis-Ngwesse \
  --repository=Flux-CouchDB \
  --branch=main \
  --path=./k8s


flux get kustomizations

kubectl get pods -n flux-system
flux check
kubectl -n flux-system delete pods --all
kubectl -n flux-system get pods                       
kubectl -n flux-system logs deployment/kustomize-controller -f
flux reconcile kustomization flux-system --with-source



minikube service couchdb-nodeport -n car-app
http://http://127.0.0.1:port/_utils/

minikube service kibana -n car-logs

minikube service car-dashboard -n car-app 

minikube service elasticsearch -n car-logs 
curl http://127.0.0.1:port/_cluster/health?pretty
curl http://127.0.0.1:65404/_cat/indices?v


kubectl delete namespace car-app
kubectl delete namespace car-logs











✅ Fix: Create a Data View in Kibana
You need to manually create a new Kibana Data View for your actual index pattern.

🛠 Steps:
Go to Kibana → Stack Management → Data Views

Click "Create data view"

Use:

Data view name: car-logs

Index pattern: car-*

Set a timestamp field (e.g., @timestamp) if available, or choose "I don’t want to use the time filter".

Save.



🔁 After Fixes, Refresh Fields in Kibana
Go to Kibana > Stack Management > Index Go to Kibana > Stack Management > Index Patterns


Go to discover to see logs that r indexed