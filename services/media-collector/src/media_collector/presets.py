from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import CollectionRule
from .schemas import Source


DEFAULT_QUERIES = {
    Source.YOUTUBE: [
        "아이돌 신곡", "K-POP 컴백", "가수 라이브 무대", "음악방송 무대", "가수 인터뷰",
        "아이돌 직캠", "K-POP 뮤직비디오", "가수 콘서트", "아이돌 팬미팅", "앨범 비하인드",
    ],
    Source.NEWS: ["K-POP 컴백", "아이돌 신곡", "가수 콘서트", "아이돌 팬미팅", "음원 차트", "가수 인터뷰"],
    Source.X: ["K-POP comeback", "K-POP new release", "K-POP concert", "K-POP fan meeting", "K-POP live stage"],
}


def ensure_default_queries(db: Session, source: Source) -> None:
    has_any = db.scalar(select(CollectionRule.id).where(CollectionRule.source == source.value).limit(1))
    if has_any is not None:
        return
    db.add_all(CollectionRule(source=source.value, query=query, enabled=True) for query in DEFAULT_QUERIES[source])
    db.commit()
