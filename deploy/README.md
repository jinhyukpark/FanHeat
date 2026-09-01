# FANHEAT 단일 EC2 배포

## 구성

- Amazon Linux 2023 EC2 한 대 (`t3.small` 기본값)
- Docker Compose의 Caddy 웹/PWA 컨테이너
- React 사용자·관리자 화면은 Supabase Auth, Database, Storage에 직접 연결
- Elastic IP, 암호화된 20GB gp3 볼륨, IMDSv2 강제
- SSH는 배포를 실행한 공인 IP의 `/32` 대역에만 허용

Supabase 데이터베이스, Auth, Storage는 기존 프로젝트를 그대로 사용합니다.

## 1. 운영 환경값 준비

```bash
cp deploy/frontend.env.example deploy/frontend.env
```

Supabase URL과 publishable key를 실제 운영 값으로 교체합니다. 이 파일은 Git에서 제외됩니다.

도메인 연결 전에는 `SITE_ADDRESS=:80`으로 시작할 수 있습니다. 도메인의 A 레코드를 Elastic IP로 연결한 뒤 `SITE_ADDRESS=example.com`처럼 바꾸고 재배포하면 Caddy가 HTTPS 인증서를 자동 발급합니다.

## 2. EC2 생성

개인 AWS 계정이나 일반 AWS 콘솔 계정은 브라우저 기반 임시 인증을 사용합니다. 별도의 IAM Identity Center 주소를 받은 조직 계정만 `aws configure sso`를 사용하세요.

```bash
aws login --region ap-northeast-2
aws sts get-caller-identity
```

브라우저에서 AWS 콘솔 로그인을 마친 뒤 두 번째 명령에서 계정 정보가 출력되면 인증이 완료된 것입니다. 기본값으로 서울 리전과 `fanheat-deploy` 키 페어를 사용하며, 키가 없으면 `deploy/.keys/fanheat-deploy.pem`에 새로 생성합니다.

```bash
export AWS_REGION=ap-northeast-2
./deploy/aws/create-stack.sh
```

기본 VPC와 기본 퍼블릭 서브넷을 자동 선택합니다. 별도 VPC를 사용하면 `VPC_ID`, `SUBNET_ID`, `SSH_CIDR`도 지정할 수 있습니다.

## 3. 애플리케이션 배포

```bash
export AWS_REGION=ap-northeast-2
./deploy/aws/deploy.sh
```

업데이트도 같은 배포 명령을 다시 실행하면 됩니다. 상태 확인은 EC2에서 다음 명령을 사용합니다.

```bash
cd /opt/fanheat
docker compose ps
docker compose logs --tail=200 web
```

사용자 화면은 `/`, React 관리자 화면은 `/admin`입니다. 관리자 권한은 Supabase 사용자의 `app_metadata.role=admin` 값과 데이터베이스 RLS 정책으로 검증합니다.
