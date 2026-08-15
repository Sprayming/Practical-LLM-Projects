#!/usr/bin/env bash
# 一键申请 Let's Encrypt 证书并自动改写 Nginx 配置（启用 HTTPS）
#
# 用法：
#   ./setup-ssl.sh rag.yourdomain.com you@example.com
#
# 前置：
#   1. 域名已解析到本机公网 IP（A 记录）
#   2. 已部署 Nginx 且本文件已软链到 sites-enabled（80 端口可访问）
#   3. 已安装 certbot + nginx 插件：sudo apt-get install -y certbot python3-certbot-nginx
set -euo pipefail

DOMAIN="${1:?用法: ./setup-ssl.sh <域名> <邮箱>}"
EMAIL="${2:-admin@example.com}"

echo ">>> 为 $DOMAIN 申请证书（certbot --nginx 会自动改写 Nginx 配置启用 443）..."
sudo certbot --nginx \
  -d "$DOMAIN" \
  --non-interactive \
  --agree-tos \
  -m "$EMAIL" \
  --redirect

echo ">>> 测试自动续期..."
sudo certbot renew --dry-run

echo "✅ 证书已申请并启用，Nginx 已配置 HTTPS。访问 https://$DOMAIN"
echo "   证书每 90 天自动续期（certbot 自带 systemd timer，无需手动干预）。"
