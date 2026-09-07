import './legal.css'

const effectiveDate = '2026년 9월 7일'

const privacySections = [
  ['1. 개인정보의 처리 목적', ['회원 가입과 본인 확인, 서비스 제공 및 계정 관리', '포스트·댓글·북마크·투표 등 커뮤니티 기능 운영', '부정 이용 방지, 서비스 안정성 확보 및 고객 문의 대응', '팬 사진 공유와 관리자 검토, 서비스 품질 개선']],
  ['2. 처리하는 개인정보 항목', ['필수: 이메일 주소, 인증 식별자, 가입·로그인 기록', '선택: 표시 이름, 프로필 이미지, 자기소개', '서비스 이용 과정: 포스트, 댓글, 북마크, 투표, 업로드 파일, 접속 정보와 오류 기록', '팬 사진 공유 시: 제출자 ID, 설명, 이미지 파일과 이미지 규격 정보']],
  ['3. 보유 및 이용 기간', ['회원 정보는 회원 탈퇴 시까지 보관하며 법령상 보존 의무가 있으면 해당 기간 동안 별도 보관합니다.', '게시물과 댓글은 사용자가 삭제하거나 운영 정책에 따라 삭제될 때까지 보관합니다.', '팬 사진 제출 자료는 검토 종료 또는 이용 목적 달성 후 지체 없이 삭제합니다.', '보안·접속 기록은 안정적인 서비스 운영을 위해 필요한 최소 기간만 보관합니다.']],
  ['4. 개인정보의 처리 위탁 및 국외 이전', ['FANHEAT는 인증, 데이터베이스와 파일 저장을 위해 Supabase 서비스를 사용합니다.', '서비스 운영 과정에서 데이터가 Supabase가 운영하는 국외 인프라에서 처리될 수 있습니다.', '위탁 업체와 처리 위치 또는 목적이 변경되면 이 방침을 통해 안내합니다.']],
  ['5. 개인정보의 파기', ['보유 기간이 끝나거나 처리 목적이 달성된 개인정보는 복구할 수 없는 방법으로 파기합니다.', '전자 파일은 재생할 수 없는 기술적 방법으로 삭제하고 출력물은 분쇄 또는 소각합니다.']],
  ['6. 이용자의 권리', ['이용자는 자신의 개인정보 열람, 정정, 삭제, 처리 정지와 회원 탈퇴를 요청할 수 있습니다.', '권리 행사는 개인정보 보호권 페이지 또는 고객 지원 이메일을 통해 요청할 수 있습니다.', '법령상 제한 사유가 없는 한 본인 확인 후 지체 없이 처리합니다.']],
  ['7. 안전성 확보 조치', ['데이터베이스 행 단위 접근 제어(RLS)를 적용하여 계정별 접근 범위를 제한합니다.', '관리자 권한은 일반 회원 권한과 분리하며 관리자 작업은 감사 로그로 기록합니다.', '비공개 파일에는 짧은 유효기간의 서명 URL을 사용하고 공개 키와 비밀 키를 분리합니다.']],
  ['8. 개인정보 보호 문의', ['개인정보 관련 문의와 권리 요청: support@fanheat.app', '요청 내용과 회신받을 이메일을 함께 보내 주시면 확인 후 답변드립니다.']],
]

const rightsSections = [
  ['내 개인정보 확인', ['마이페이지에서 표시 이름, 프로필 이미지, 자기소개와 작성 콘텐츠를 확인할 수 있습니다.', '추가적인 개인정보 사본이 필요하면 고객 지원으로 데이터 열람을 요청할 수 있습니다.']],
  ['정정 및 삭제', ['마이페이지에서 직접 수정할 수 없는 정보는 고객 지원으로 정정을 요청할 수 있습니다.', '포스트, 댓글, 북마크와 업로드 사진은 각 기능에서 삭제하거나 운영자에게 삭제를 요청할 수 있습니다.']],
  ['처리 정지 및 회원 탈퇴', ['개인정보 처리를 원하지 않으면 서비스 이용 중단 또는 회원 탈퇴를 요청할 수 있습니다.', '탈퇴 시 법령상 보존 대상이 아닌 계정 정보는 삭제되며, 공개 콘텐츠의 삭제 범위는 별도로 확인합니다.']],
  ['요청 방법', ['support@fanheat.app으로 요청 유형, 계정 이메일, 요청 내용을 보내 주세요.', '본인 확인이 필요한 경우 최소한의 추가 정보를 요청할 수 있습니다.', '접수 후 처리 진행 상황과 결과를 이메일로 안내합니다.']],
]

const termsSections = [
  ['1. 목적', ['이 약관은 FANHEAT가 제공하는 K-POP 팬 커뮤니티 서비스의 이용 조건과 회원 및 운영자의 권리·의무를 정합니다.']],
  ['2. 계정과 회원의 의무', ['회원은 정확한 정보를 사용하고 계정 접근 정보를 안전하게 관리해야 합니다.', '타인의 계정, 개인정보, 저작권과 초상권을 침해해서는 안 됩니다.', '서비스 운영을 방해하거나 부정한 방법으로 HEAT, FAN CREDIT, 투표 결과를 조작해서는 안 됩니다.']],
  ['3. 회원 콘텐츠와 이용 허락', ['회원이 직접 작성하거나 적법하게 권리를 보유한 콘텐츠의 권리는 원칙적으로 회원 또는 해당 권리자에게 있습니다.', '회원은 자신이 게시하는 글·사진·영상·음원 등 콘텐츠를 업로드하고 서비스에서 공개할 권한이 있음을 확인해야 합니다.', '회원은 서비스 제공, 저장, 화면 노출, 기기별 변환, 신고 처리와 운영상 백업에 필요한 범위에서 FANHEAT가 해당 콘텐츠를 비독점적이고 무상으로 이용하도록 허락합니다. 이 허락은 콘텐츠가 삭제되면 합리적인 백업·법적 보존 기간을 제외하고 종료됩니다.', '회원은 콘텐츠에 포함된 제3자의 개인정보, 성명, 초상, 음성 또는 그 밖의 인격적·경제적 권리에 필요한 동의를 직접 확인해야 합니다.']],
  ['4. 연예인 이미지와 제3자 콘텐츠', ['소속사, 방송사, 언론사 또는 아티스트의 공식 채널에서 공개한 사진·티저·프로필·앨범 이미지라는 사정만으로 자유로운 복제·업로드·재배포가 허용되는 것은 아닙니다.', '회원은 권리자의 허락, 적용되는 라이선스 또는 법령상 정당한 이용 근거가 없는 제3자 이미지를 FANHEAT 서버에 직접 업로드해서는 안 됩니다. 출처를 표시하거나 비영리 팬 활동으로 이용한다는 사정만으로 필요한 권한이 자동으로 생기지는 않습니다.', '가능하면 원본을 복제하여 올리는 대신 권리자가 제공한 공식 게시물 URL이나 해당 플랫폼이 허용하는 공식 공유·임베드 기능을 사용해야 하며, 원문 링크·권리자·출처와 적용되는 이용 조건을 함께 표시해야 합니다.', '초상이나 성명 등을 상품 판매, 광고, 후원 또는 그 밖의 영리적 홍보에 이용하려는 경우에는 관련 권리자로부터 필요한 별도 허락을 받아야 합니다.']],
  ['5. 금지 콘텐츠', ['저작권, 저작인접권, 상표권, 초상권, 개인정보 또는 그 밖의 제3자 권리를 침해하는 콘텐츠를 게시해서는 안 됩니다.', '워터마크나 권리관리정보를 제거한 자료, 접근 제한을 우회해 얻은 자료, 출처나 권리자를 허위로 표시한 자료를 게시해서는 안 됩니다.', '공식 게시물이 삭제·비공개 처리되었거나 임베드 제공자가 표시를 중단한 경우 이를 우회하여 다시 제공해서는 안 됩니다.']],
  ['6. 권리 침해 신고와 게시 중단', ['권리자 또는 정당한 대리인은 support@fanheat.app으로 대상 콘텐츠의 위치, 침해 주장 내용, 권리 관계를 확인할 수 있는 자료와 연락처를 보내 게시 중단을 요청할 수 있습니다.', 'FANHEAT는 권리 침해 신고 또는 명백한 침해 정황을 확인하면 관련 법령과 운영 절차에 따라 콘텐츠를 임시 숨김·삭제하거나 접근을 제한하고 게시자에게 필요한 내용을 알릴 수 있습니다.', '게시자는 적법한 권한이나 법령상 이용 근거가 있다고 판단하면 관련 자료를 첨부하여 재검토 또는 재게시를 요청할 수 있습니다. 정당한 권리 없이 중단이나 재개를 요구해서는 안 됩니다.', '반복적으로 타인의 권리를 침해하거나 신고 절차를 악용하는 계정은 게시 제한, 기능 제한 또는 이용계약 해지 대상이 될 수 있습니다.']],
  ['7. 서비스 이용 제한', ['법령 또는 약관 위반, 권리 침해, 괴롭힘, 스팸, 조작 행위가 확인되면 콘텐츠 숨김이나 계정 이용 제한 조치를 할 수 있습니다.', '중대한 위반이 아닌 경우 가능한 범위에서 사전 안내와 소명 기회를 제공합니다.']],
  ['8. 서비스 변경과 중단', ['서비스 개선, 점검, 장애 또는 외부 서비스 변경으로 기능의 일부가 변경되거나 일시 중단될 수 있습니다.', '중요한 변경은 서비스 화면 또는 등록된 연락 수단으로 안내합니다.']],
  ['9. 책임 제한', ['FANHEAT는 회원이 작성한 정보의 정확성이나 외부 플랫폼 콘텐츠의 지속적인 제공을 보증하지 않습니다.', '회원에게 콘텐츠 관련 책임이 있다는 약정만으로 FANHEAT의 법령상 의무나 책임이 배제되는 것은 아니며, FANHEAT는 접수된 권리 침해 신고를 운영 절차와 관련 법령에 따라 처리합니다.', '고의 또는 중대한 과실이 없는 한 불가항력이나 회원의 귀책으로 발생한 손해에 책임을 지지 않습니다.']],
  ['10. 문의', ['서비스 이용 및 권리 침해 문의: support@fanheat.app']],
]

const pages = {
  '/legal/privacy': { eyebrow: 'PRIVACY POLICY', title: '개인정보 처리방침', intro: 'FANHEAT는 이용자의 개인정보를 필요한 범위에서 안전하고 투명하게 처리합니다.', sections: privacySections },
  '/legal/privacy-rights': { eyebrow: 'YOUR PRIVACY RIGHTS', title: '개인정보 보호권', intro: '이용자는 자신의 개인정보에 대해 다음과 같은 권리를 행사할 수 있습니다.', sections: rightsSections },
  '/legal/terms': { eyebrow: 'TERMS OF SERVICE', title: '서비스 이용약관', intro: 'FANHEAT를 안전하고 즐거운 팬 커뮤니티로 운영하기 위한 기본 이용 조건입니다.', sections: termsSections },
}

const legalNavigation = [
  ['/legal/terms', '서비스 이용약관'],
  ['/legal/privacy', '개인정보 처리방침'],
  ['/support', '고객지원'],
]

function SupportPage() {
  return <LegalLayout eyebrow="CUSTOMER SUPPORT" title="고객 지원" intro="서비스 이용 중 궁금한 점이나 권리 침해 신고가 있다면 아래 채널로 알려주세요."><section><h2>문의 채널</h2><p>이메일: <a href="mailto:support@fanheat.app">support@fanheat.app</a></p><p>계정 이메일, 문제가 발생한 화면, 발생 시각과 내용을 함께 보내면 더 빠르게 확인할 수 있습니다.</p></section><section><h2>신고 및 권리 침해</h2><p>저작권·초상권·개인정보 침해 신고에는 신고자 연락처, 대상 콘텐츠 URL, 침해 주장 내용과 권리자 또는 정당한 대리인임을 확인할 수 있는 자료를 포함해 주세요.</p><p>게시 중단 통지를 받은 게시자는 적법한 이용 권한이나 법령상 이용 근거를 확인할 수 있는 자료와 함께 재검토를 요청할 수 있습니다.</p><p>긴급한 보안 문제에는 제목 앞에 <b>[보안]</b>을 표시해 주세요.</p></section></LegalLayout>
}

function LegalLayout({ eyebrow, title, intro, children }) {
  const currentPath = window.location.pathname === '/legal/privacy-rights' ? '/legal/privacy' : window.location.pathname
  return <div className="legal-page">
    <header className="legal-header">
      <div className="legal-brands">
        <a className="teragraph-brand" href="/" aria-label="TeraGraph 홈"><svg viewBox="0 0 44 44" aria-hidden="true"><path d="M22 3v38M3 22h38M8.5 8.5l27 27M35.5 8.5l-27 27"/><circle cx="22" cy="22" r="7"/><circle cx="22" cy="3" r="2.5"/><circle cx="41" cy="22" r="2.5"/><circle cx="22" cy="41" r="2.5"/><circle cx="3" cy="22" r="2.5"/></svg><strong><span>Tera</span>Graph</strong></a>
        <i aria-hidden="true" />
        <a className="legal-fanheat-brand" href="/"><img src="/images/fanheat-logo.png" alt="" /><strong>FAN HEAT</strong></a>
      </div>
      <label className="legal-language"><span aria-hidden="true">◎</span><select defaultValue="ko" aria-label="문서 언어"><option value="ko">한국어</option><option value="en">English</option><option value="ja">日本語</option></select></label>
    </header>
    <main className="legal-layout">
      <aside><nav aria-label="정책 및 고객지원">{legalNavigation.map(([path, label]) => <a className={currentPath === path ? 'active' : ''} href={path} aria-current={currentPath === path ? 'page' : undefined} key={path}>{label}</a>)}</nav></aside>
      <section className="legal-content"><header className="legal-title"><small>{eyebrow}</small><h1>{title}</h1><p>{intro}</p>{currentPath !== '/support' && <time>시행일 {effectiveDate}</time>}</header><article className="legal-document">{children}</article></section>
    </main>
    <footer><span>© 2026 TeraGraph · FAN HEAT</span><a href="mailto:support@fanheat.app">support@fanheat.app</a></footer>
  </div>
}

export default function LegalPage() {
  if (window.location.pathname === '/support') return <SupportPage />
  const page = pages[window.location.pathname] || pages['/legal/privacy']
  return <LegalLayout eyebrow={page.eyebrow} title={page.title} intro={page.intro}>{page.sections.map(([title, paragraphs]) => <section key={title}><h2>{title}</h2>{paragraphs.map(paragraph => <p key={paragraph}>{paragraph}</p>)}</section>)}</LegalLayout>
}
