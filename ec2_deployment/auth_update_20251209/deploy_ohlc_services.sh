#!/bin/bash
# Deploy updated OHLC aggregator services to EC2

set -e

EC2_IP="54.64.254.201"
SSH_KEY="/Users/yousuke/.ssh/convex-keypair.pem"
EC2_USER="ubuntu"

echo "📦 Deploying updated OHLC aggregator services..."

# Copy service files
scp -i "$SSH_KEY" \
    data_acquisition_system/token_price_tracker/token_ohlc_aggregator.service \
    data_acquisition_system/usdjpy_price_tracker/usdjpy_ohlc_aggregator.service \
    "$EC2_USER@$EC2_IP:/tmp/"

# Deploy and reload on EC2
ssh -i "$SSH_KEY" "$EC2_USER@$EC2_IP" << 'EOF'
    echo "📋 Copying service files to systemd..."
    sudo cp /tmp/token_ohlc_aggregator.service /etc/systemd/system/
    sudo cp /tmp/usdjpy_ohlc_aggregator.service /etc/systemd/system/
    
    echo "🔄 Reloading systemd daemon..."
    sudo systemctl daemon-reload
    
    echo "✅ Services updated successfully"
    echo "📊 Service status:"
    systemctl status token_ohlc_aggregator.timer --no-pager || true
    systemctl status usdjpy_ohlc_aggregator.timer --no-pager || true
EOF

echo "✅ Deployment complete!"
