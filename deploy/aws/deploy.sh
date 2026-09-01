#!/usr/bin/env bash
set -euo pipefail

AWS_BIN="${AWS_BIN:-aws}"
AWS_REGION="${AWS_REGION:-ap-northeast-2}"
STACK_NAME="${STACK_NAME:-fanheat-production}"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
EC2_KEY_NAME="${EC2_KEY_NAME:-fanheat-deploy}"
SSH_KEY_PATH="${SSH_KEY_PATH:-$PROJECT_ROOT/deploy/.keys/$EC2_KEY_NAME.pem}"
REMOTE_DIR="/opt/fanheat"
REMOTE_CURRENT="$REMOTE_DIR/current"
REMOTE_NEXT="$REMOTE_DIR/.next"

if [[ -z "$SSH_KEY_PATH" || ! -f "$SSH_KEY_PATH" ]]; then
  echo "SSH_KEY_PATH에 EC2 키 페어의 .pem 파일 경로를 지정하세요." >&2
  exit 1
fi
if [[ ! -f deploy/frontend.env ]]; then
  echo "deploy/frontend.env를 example 파일에서 복사해 운영 값을 입력하세요." >&2
  exit 1
fi

PUBLIC_IP="$("$AWS_BIN" cloudformation describe-stacks --region "$AWS_REGION" --stack-name "$STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='PublicIp'].OutputValue" --output text)"
if [[ -z "$PUBLIC_IP" || "$PUBLIC_IP" == "None" ]]; then
  echo "CloudFormation 스택에서 PublicIp를 찾지 못했습니다." >&2
  exit 1
fi

ARCHIVE="$(mktemp -t fanheat-deploy.XXXXXX.tar.gz)"
trap 'rm -f "$ARCHIVE"' EXIT

COPYFILE_DISABLE=1 tar -C "$PROJECT_ROOT" \
  --no-xattrs \
  --exclude='web/.env*' \
  --exclude='web/node_modules' \
  --exclude='web/dist' \
  --exclude='*.log' \
  -czf "$ARCHIVE" \
  compose.yaml \
  web \
  deploy/Caddyfile \
  deploy/frontend.env

SSH_ARGS=(-i "$SSH_KEY_PATH" -o StrictHostKeyChecking=accept-new)
scp "${SSH_ARGS[@]}" "$ARCHIVE" "ec2-user@$PUBLIC_IP:/tmp/fanheat.tar.gz"
ssh "${SSH_ARGS[@]}" "ec2-user@$PUBLIC_IP" \
  "set -e; sudo cloud-init status --wait >/dev/null 2>&1 || true; command -v docker >/dev/null; docker compose version >/dev/null; docker buildx version >/dev/null; mkdir -p '$REMOTE_DIR'; rm -rf '$REMOTE_NEXT'; mkdir -p '$REMOTE_NEXT'; tar -xzf /tmp/fanheat.tar.gz -C '$REMOTE_NEXT'; rm -f /tmp/fanheat.tar.gz; cd '$REMOTE_NEXT'; docker compose --project-name fanheat --env-file deploy/frontend.env up -d --build --remove-orphans; curl --fail --silent --show-error --retry 12 --retry-all-errors --retry-delay 2 http://127.0.0.1/healthz >/dev/null; rm -rf '$REMOTE_CURRENT.previous'; if [[ -d '$REMOTE_CURRENT' ]]; then mv '$REMOTE_CURRENT' '$REMOTE_CURRENT.previous'; fi; mv '$REMOTE_NEXT' '$REMOTE_CURRENT'"

curl --fail --silent --show-error --retry 12 --retry-all-errors --retry-delay 2 "http://$PUBLIC_IP/healthz" >/dev/null
echo "배포 및 헬스 체크 완료: http://$PUBLIC_IP"
