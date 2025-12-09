#!/bin/bash
# =====================================
# Update EC2 env and restart service
# =====================================

set -e

EC2_IP="54.64.254.201"
KEY_FILE="/Users/yousuke/.ssh/convex-keypair.pem"
USER="ubuntu"

echo "Using: $EC2_IP with key $KEY_FILE"

# 1. deploy the fixed service file
./ec2_deployment/deploy_token_service_fix.sh -h $EC2_IP -k $KEY_FILE

# 2. Prompt for AWS Key update
echo "=============================================="
echo "To update AWS credentials, please run:"
echo "./ec2_deployment/update_ec2_keys.sh -h $EC2_IP -k $KEY_FILE"
echo "=============================================="
