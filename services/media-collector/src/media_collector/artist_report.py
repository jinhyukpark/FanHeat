"""Explain persisted collection gaps without rerunning or modifying a job."""


def completion_issues(report):
    if not isinstance(report, dict):
        return []
    issues = []
    for reason in report.get('missing') or []:
        reason = str(reason)
        detail = reason
        action = '수집 근거와 진행 로그를 확인하고 공식 출처를 보완한 뒤 재수집하세요.'
        for scope, label in [('biography', '소개 본문'), ('history', '연혁'), ('awards', '수상')]:
            if scope in reason:
                detail = f'{label}: 검증된 본문을 작성하지 못했습니다. 현재 보고서만으로는 근거 부족과 LLM 호출 실패를 구분할 수 없습니다.'
                action = f'{label}이 담긴 공식 페이지·기사 URL을 추가하고 LLM 단계의 오류 로그를 확인한 뒤 재수집하세요. 확인되지 않은 내용은 임의 생성하지 않습니다.'
        if 'SNS' in reason:
            action = '소속사나 아티스트 공식 홈페이지에서 연결한 SNS 주소를 공식 채널 URL에 추가해 재수집하세요.'
        elif '앨범 목록' in reason:
            action = '공식 디스코그래피 또는 음반사 앨범 목록 페이지를 추가해 재수집하세요.'
        elif '수록곡' in reason:
            empty = [str(a.get('title', '제목 없음')) for a in report.get('evidence', []) if not a.get('tracks')]
            detail += ' · 수록곡 미확인 앨범: ' + (', '.join(empty) if empty else '보고서에 수록곡 목록이 없습니다')
            action = '해당 앨범의 공식 트랙리스트 페이지를 추가하고 곡 수집을 선택해 재수집하세요.'
        elif '영상 미연결' in reason:
            tracks = [f"{a.get('title', '')} / {t.get('title', '')}" for a in report.get('evidence', []) for t in a.get('tracks', []) if not t.get('url')]
            if tracks:
                detail += ' · 대상: ' + ', '.join(tracks)
            action = '공식 YouTube 채널 주소와 영상 공개 여부를 확인하세요. 재수집 후에도 없는 공식 영상은 미연결 상태로 유지합니다.'
        elif '탐색 한도' in reason:
            action = '로그에서 접근 실패·한도 도달 출처를 확인하고 해당 공식 상세 URL을 직접 추가해 재수집하세요.'
        elif '데뷔·소속사·팬덤' in reason:
            detail = '프로필 자동 검증이 완전히 지원되지 않아 데뷔·소속사·팬덤을 모두 검증한 완료 상태로 처리하지 않았습니다. 모든 값이 비어 있다는 뜻은 아닙니다.'
            action = '관리페이지의 프로필 값과 공식 소개를 대조해 누락·오류를 수정하세요. 재수집만으로 이 검증 제한이 해결되지는 않습니다.'
        elif '갤러리' in reason:
            gallery = report.get('gallery_review') or {}
            items = gallery.get('items') or []
            counts = {key: sum(i.get('decision') == key for i in items) for key in ('photo_candidate', 'exclude', 'review')}
            detail = f"이미지 판별 {len(items)}개: 활동 사진 후보 {counts['photo_candidate']}개, 배너·상품 등 제외 {counts['exclude']}개, 확인 필요 {counts['review']}개. 미검토 {gallery.get('remaining', 0)}개."
            if gallery.get('storage') == 'source_url_only':
                detail += ' 현재 원본 파일을 서버에 복사하지 않고 출처 URL만 등록합니다.'
            elif not gallery:
                detail += ' 이 작업에는 비전 판별 상세 기록이 없습니다.'
            action = '활동 사진 후보를 관리페이지에서 검토하세요. 배너는 제외하고 미검토 이미지는 공식 사진 페이지로 범위를 좁혀 재수집하세요. 원본 서버 저장은 별도 구현이 필요합니다.'
        elif '기존 공개 데이터 보호' in reason:
            action = '새 수집 근거를 기존 공개 내용과 비교해 관리페이지에서 승인·수정하세요. 기존 공개 데이터는 자동으로 덮어쓰지 않았습니다.'
        issues.append({'title': reason, 'detail': detail, 'action': action})
    return issues
