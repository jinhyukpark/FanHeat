#!/usr/bin/env bash
set -euo pipefail

AWS_BIN="${AWS_BIN:-aws}"
AWS_REGION="${AWS_REGION:-ap-northeast-2}"
STACK_NAME="${STACK_NAME:-fanheat-production}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.small}"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
EC2_KEY_NAME="${EC2_KEY_NAME:-fanheat-deploy}"
SSH_KEY_PATH="${SSH_KEY_PATH:-$PROJECT_ROOT/deploy/.keys/$EC2_KEY_NAME.pem}"

"$AWS_BIN" sts get-caller-identity >/dev/null

if ! "$AWS_BIN" ec2 describe-key-pairs --region "$AWS_REGION" --key-names "$EC2_KEY_NAME" >/dev/null 2>&1; then
  mkdir -p "$(dirname "$SSH_KEY_PATH")"
  "$AWS_BIN" ec2 create-key-pair \
    --region "$AWS_REGION" \
    --key-name "$EC2_KEY_NAME" \
    --key-type ed25519 \
    --query KeyMaterial \
    --output text > "$SSH_KEY_PATH"
  chmod 600 "$SSH_KEY_PATH"
  echo "새 EC2 키 페어를 생성했습니다: $SSH_KEY_PATH"
elif [[ ! -f "$SSH_KEY_PATH" ]]; then
  echo "AWS에 '$EC2_KEY_NAME' 키 페어가 있지만 로컬 개인 키가 없습니다." >&2
  echo "EC2_KEY_NAME을 다른 이름으로 지정하거나 SSH_KEY_PATH에 기존 .pem 경로를 지정하세요." >&2
  exit 1
fi

VPC_ID="${VPC_ID:-$("$AWS_BIN" ec2 describe-vpcs --region "$AWS_REGION" --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)}"
if [[ -z "$VPC_ID" || "$VPC_ID" == "None" ]]; then
  echo "기본 VPC가 없습니다. VPC_ID와 SUBNET_ID를 직접 지정하세요." >&2
  exit 1
fi

SUBNET_ID="${SUBNET_ID:-$("$AWS_BIN" ec2 describe-subnets --region "$AWS_REGION" --filters "Name=vpc-id,Values=$VPC_ID" Name=default-for-az,Values=true --query 'Subnets | sort_by(@, &AvailabilityZone)[0].SubnetId' --output text)}"
if [[ -z "$SUBNET_ID" || "$SUBNET_ID" == "None" ]]; then
  echo "사용 가능한 기본 서브넷이 없습니다. SUBNET_ID를 직접 지정하세요." >&2
  exit 1
fi

SSH_CIDR="${SSH_CIDR:-$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')/32}"

"$AWS_BIN" cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME" \
  --template-file "$(cd "$(dirname "$0")" && pwd)/cloudformation.yml" \
  --parameter-overrides \
    VpcId="$VPC_ID" \
    SubnetId="$SUBNET_ID" \
    KeyName="$EC2_KEY_NAME" \
    SshCidr="$SSH_CIDR" \
    InstanceType="$INSTANCE_TYPE"

"$AWS_BIN" cloudformation describe-stacks \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs' \
  --output table

echo "SSH 개인 키: $SSH_KEY_PATH"
