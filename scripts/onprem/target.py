#!/usr/bin/env python3
"""Validate the device identity before scheduling a self-hosted job."""
import os
import re


def validate(target, label, runner, cluster):
    label = label or target
    if target not in ("aws", "gcp", "onprem"):
        raise ValueError("target must be aws, gcp or onprem")
    if target != "onprem":
        if label != target:
            raise ValueError("cloud target and notification target differ")
        return
    if not re.fullmatch(r"onprem(?:-[a-z0-9][a-z0-9-]*)?", label) or runner != label:
        raise ValueError("onprem device and runner label differ")
    if not re.fullmatch(r"k3d-[a-z0-9][a-z0-9-]*", cluster):
        raise ValueError("onprem requires a k3d context")
    # The installed runner's ONPREM_CLUSTER is checked again by kube-access.
    # Cluster names are local configuration; no owner/person name is assumed here.



if __name__ == "__main__":
    validate(os.environ["TARGET"], os.environ.get("TARGET_LABEL", ""),
             os.environ["RUNNER_LABEL"], os.environ["CLUSTER"])
