# Creating the pia-vpn-credentials Secret

The PIA VPN sidecar (gluetun) needs your Private Internet Access credentials to
authenticate. These are stored as a Kubernetes Secret and injected as environment
variables into the `pia-vpn` init container.

> **Note**: Use your PIA **username** (e.g. `p1234567`) and **password** — the same
> credentials you use to log in to the PIA website. Not your email address.

## Create the secret

```bash
kubectl create secret generic pia-vpn-credentials \
  --namespace media \
  --from-literal=username=<YOUR_PIA_USERNAME> \
  --from-literal=password=<YOUR_PIA_PASSWORD>
```

Verify it was created:

```bash
kubectl get secret pia-vpn-credentials -n media
```

## Rotate credentials

If you change your PIA password:

```bash
kubectl delete secret pia-vpn-credentials -n media
kubectl create secret generic pia-vpn-credentials \
  --namespace media \
  --from-literal=username=<YOUR_PIA_USERNAME> \
  --from-literal=password=<YOUR_PIA_PASSWORD>
```

## Choosing a VPN region

By default the CronJob is configured for `SERVER_REGIONS: "US East"`. To use a
different region, edit that value in `k8s/cronjob.yaml`. Full list of PIA regions
supported by gluetun:

https://github.com/qdm12/gluetun-wiki/blob/main/setup/providers/private-internet-access.md

To let gluetun auto-select the fastest server, remove the `SERVER_REGIONS` env var
entirely from the `pia-vpn` init container.

## Kubernetes version requirement

The VPN sidecar uses the **native sidecar init container** feature (`restartPolicy: Always`
on an init container), which requires **Kubernetes 1.29 or later**. If your cluster is
older, contact the cluster admin or upgrade before deploying.

## Verify VPN is working

After a job run, check the pia-vpn container logs:

```bash
# Get the most recent job pod name
kubectl get pods -n media -l app=yt-sync --sort-by=.metadata.creationTimestamp

# Tail the VPN sidecar logs
kubectl logs -n media <pod-name> -c pia-vpn
```

You should see gluetun log lines indicating a successful OpenVPN connection, e.g.:
```
INFO [openvpn] Connected with settings ...
INFO [ip getter] Public IP address is X.X.X.X (country: United States, ...
```
