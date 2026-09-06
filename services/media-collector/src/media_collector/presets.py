from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import CollectionRule
from .schemas import Source


DEFAULT_QUERIES = {
    Source.YOUTUBE: [
        "아이돌 신곡", "K-POP 컴백", "가수 라이브 무대", "음악방송 무대", "가수 인터뷰",
        "아이돌 직캠", "K-POP 뮤직비디오", "가수 콘서트", "아이돌 팬미팅", "앨범 비하인드",
    ],
    Source.NEWS: [
        "아이돌 컴백", "아이돌 신곡", "아이돌 콘서트", "아이돌 팬미팅", "아이돌 음원 차트",
        "아이돌 인터뷰", "아이돌 직캠", "아이돌 공항패션", "걸그룹 컴백", "보이그룹 컴백",
        "아이돌 쇼케이스",
    ],
    Source.X: ["K-POP comeback", "K-POP new release", "K-POP concert", "K-POP fan meeting", "K-POP live stage"],
}


DEFAULT_NEWS_SOURCES = [
    {
        "name": "뉴시스 연예",
        "domains": ["newsis.com"],
        "source_url": "https://www.newsis.com/entertainment/",
        "rss_url": "https://nwww.newsis.com/RSS/entertain.xml",
        "enabled": True,
        "allow_thumbnail_preview": True,
    },
    {
        "name": "매일경제 문화·연예",
        "domains": ["mk.co.kr"],
        "source_url": "https://www.mk.co.kr/news/culture/",
        "rss_url": "https://www.mk.co.kr/rss/30000023/",
        "enabled": True,
        "allow_thumbnail_preview": True,
    },
    {
        "name": "MBN 연예",
        "domains": ["mbn.co.kr"],
        "source_url": None,
        "rss_url": "https://www.mbn.co.kr/rss/enter/",
        "enabled": True,
        "allow_thumbnail_preview": True,
    },
    {
        "name": "연합뉴스 연예",
        "domains": ["yna.co.kr"],
        "source_url": "https://www.yna.co.kr/entertainment/index",
        "rss_url": "https://www.yna.co.kr/rss/entertainment.xml",
        "enabled": True,
        "allow_thumbnail_preview": True,
    },
    {
        "name": "스타뉴스",
        "domains": ["starnewskorea.com", "starnewsk.com"],
        "source_url": "https://www.starnewskorea.com/entertainment/tv",
        "rss_url": "https://rss.mt.co.kr/st_news.xml",
        "enabled": True,
        "allow_thumbnail_preview": True,
    },
    {"name": "스포츠경향", "domains": ["sports.khan.co.kr"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
    {"name": "뉴스엔", "domains": ["newsen.com"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
    {"name": "스포츠서울", "domains": ["sportsseoul.com"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
    {"name": "스포츠동아", "domains": ["sports.donga.com"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
    {"name": "뉴스1", "domains": ["news1.kr"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
    {"name": "OSEN", "domains": ["osen.co.kr"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
    {"name": "더팩트", "domains": ["news.tf.co.kr"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
    {"name": "SPOTV NEWS", "domains": ["spotvnews.co.kr"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
    {"name": "마이데일리", "domains": ["mydaily.co.kr"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
    {"name": "TV리포트", "domains": ["tvreport.co.kr"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
    {"name": "이데일리", "domains": ["edaily.co.kr"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
    {"name": "스포츠월드", "domains": ["sportsworldi.com"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
    {"name": "텐아시아", "domains": ["tenasia.co.kr"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
    {"name": "JTBC 뉴스", "domains": ["news.jtbc.co.kr"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
    {"name": "엑스포츠뉴스", "domains": ["xportsnews.com"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
    {"name": "티브이데일리", "domains": ["tvdaily.co.kr"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
    {"name": "MBC연예", "domains": ["enews.imbc.com"], "source_url": None, "rss_url": None, "enabled": True, "allow_thumbnail_preview": True},
]


def default_news_sources() -> list[dict]:
    """Return independent dictionaries so callers can safely persist or edit them."""
    return [dict(source, domains=list(source["domains"])) for source in DEFAULT_NEWS_SOURCES]


def ensure_default_queries(db: Session, source: Source) -> None:
    has_any = db.scalar(select(CollectionRule.id).where(CollectionRule.source == source.value).limit(1))
    if has_any is not None:
        return
    db.add_all(CollectionRule(source=source.value, query=query, enabled=True) for query in DEFAULT_QUERIES[source])
    db.commit()
