import { useRef, useState } from 'react'
import { deleteAdminArtist } from './lib/admin-api'

export default function AdminDeleteArtist({ artist, disabled = false }) {
  const lock = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const remove = async () => {
    if (lock.current || disabled) return
    const name = artist.name_ko || artist.name
    if (!window.confirm(`“${name}” 아티스트 전체 정보를 삭제할까요?\n\n프로필, 앨범·수록곡, 갤러리 등록 정보, 팬 연결, 투표, 수정 요청, 자동 수집 주기 설정이 함께 삭제됩니다.\n회원 계정과 작성된 게시물은 유지되며 아티스트 연결만 해제됩니다. 외부 원본 이미지와 수집 실행 기록은 삭제되지 않습니다.\n\n삭제 후 이 화면에서 복구할 수 없습니다. 정말 삭제하시겠습니까?`)) return
    lock.current = true
    setBusy(true); setError('')
    try {
      await deleteAdminArtist(artist.id)
      window.location.assign('/admin/artists')
    } catch (err) {
      setError(err.message || '삭제하지 못했습니다. 다시 시도해 주세요.')
      lock.current = false; setBusy(false)
    }
  }
  return <div className="admin-delete-artist"><button type="button" disabled={disabled || busy} onClick={remove}>{busy ? '삭제 중…' : '아티스트 전체 삭제'}</button>{error && <p role="alert">{error}</p>}</div>
}
