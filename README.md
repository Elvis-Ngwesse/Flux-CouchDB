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

COMMIT_SHA=$(git rev-parse --short HEAD)
docker buildx build \
--platform linux/amd64 \
-t dockerelvis/car-dashboard:latest \
-t dockerelvis/car-dashboard:$COMMIT_SHA \
-f Dockerfile.app \
--load .
echo $COMMIT_SHA

-----
COMMIT_SHA=$(git rev-parse --short HEAD)
docker buildx build \
--platform linux/amd64 \
-t dockerelvis/car-dashboard:latest \
-t dockerelvis/data-generator:$COMMIT_SHA \
-f Dockerfile.app \
--load .
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

minikube stop minikube delete --all
minikube delete --all --purge

🌐 

flux bootstrap github \
  --owner=Elvis-Ngwesse \
  --repository=Flux-CouchDB \
  --branch=main \
  --path=./k8s


flux get kustomizations
