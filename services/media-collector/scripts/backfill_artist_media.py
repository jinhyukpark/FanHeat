#!/usr/bin/env python3
"""Backfill licensed Commons photos and embeddable official YouTube links.

The script is intentionally conservative: it never replaces an administrator
value, only trusts the artist's stored official channel, and only publishes a
Commons image after both rights metadata and the existing vision gate pass.
"""
from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from urllib.parse import unquote

import httpx
from sqlalchemy import text

from media_collector.artist_catalog import video_match
from media_collector.commons_gallery import collect_commons_candidates
from media_collector.config import get_settings
from media_collector.db import SessionLocal
from media_collector.gallery_vision import classify_gallery


YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
NON_PHOTO_MARKERS = {
    "advertisement", "advertisment", "album_cover", "cover)", "cover.",
    "fileicon-", "logo", "repackage", "rice_wreath", "title_card", "timeline",
}


def youtube_items(client: httpx.Client, api_key: str, resource: str, **params):
    response = client.get(f"{YOUTUBE_API}/{resource}", params={**params, "key": api_key})
    if response.is_error:
        raise RuntimeError(f"YouTube {resource} HTTP {response.status_code}")
    return response.json()


def official_uploads(client: httpx.Client, api_key: str, channel_id: str, pages: int = 12):
    channel_data = youtube_items(client, api_key, "channels", part="contentDetails", id=channel_id)
    channel_rows = channel_data.get("items", [])
    if not channel_rows:
        return []
    playlist_id = channel_rows[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    if not playlist_id:
        return []
    video_ids: list[str] = []
    token = None
    for _ in range(pages):
        params = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": 50}
        if token:
            params["pageToken"] = token
        data = youtube_items(client, api_key, "playlistItems", **params)
        video_ids.extend(
            row["contentDetails"]["videoId"]
            for row in data.get("items", [])
            if row.get("contentDetails", {}).get("videoId")
        )
        token = data.get("nextPageToken")
        if not token:
            break
    videos = []
    for start in range(0, len(video_ids), 50):
        data = youtube_items(
            client,
            api_key,
            "videos",
            part="snippet,status,contentDetails",
            id=",".join(video_ids[start : start + 50]),
        )
        videos.extend(data.get("items", []))
    return videos


def aliases_for(artist) -> list[str]:
    values = [artist["name_ko"], artist["name"], re.sub(r"-q\d+$", "", artist["slug"]).replace("-", " ")]
    return list(dict.fromkeys(value for value in values if value))


def backfill_youtube(db, settings, apply: bool):
    if not settings.youtube_api_key:
        raise RuntimeError("YOUTUBE_API_KEY is not configured")
    artists = db.execute(text("""
        select id, slug, name, name_ko, youtube_channel_id
        from public.artists
        where active = true and youtube_channel_id is not null
        order by id
    """)).mappings().all()
    linked_tracks = linked_albums = 0
    per_artist = []
    with httpx.Client(timeout=30) as client:
        for artist in artists:
            videos = official_uploads(client, settings.youtube_api_key, artist["youtube_channel_id"])
            aliases = aliases_for(artist)
            rows = db.execute(text("""
                select track.id, track.title, track.youtube_url, album.id as album_id,
                       album.title as album_title, album.lead_track, album.youtube_url as album_youtube_url
                from public.artist_album_tracks track
                join public.artist_albums album on album.id = track.album_id
                where album.artist_id = :artist_id and album.active = true and track.active = true
                order by album.display_order, track.track_number
            """), {"artist_id": artist["id"]}).mappings().all()
            album_matches: dict[int, list[tuple[dict, str]]] = defaultdict(list)
            artist_links = 0
            for row in rows:
                if row["youtube_url"]:
                    album_matches[row["album_id"]].append((row, row["youtube_url"]))
                    continue
                ranked = sorted(
                    ((video_match(row["title"], video, aliases, "KR", True), video) for video in videos),
                    key=lambda pair: pair[0],
                    reverse=True,
                )
                if not ranked or not ranked[0][0]:
                    continue
                url = f"https://www.youtube.com/watch?v={ranked[0][1]['id']}"
                album_matches[row["album_id"]].append((row, url))
                artist_links += 1
                if apply:
                    db.execute(
                        text("update public.artist_album_tracks set youtube_url=:url, updated_at=now() where id=:id and youtube_url is null"),
                        {"id": row["id"], "url": url},
                    )
            artist_album_links = 0
            for album_id, matches in album_matches.items():
                row = matches[0][0]
                if row["album_youtube_url"]:
                    continue
                lead_key = re.sub(r"[^0-9a-z가-힣]+", "", (row["lead_track"] or "").casefold())
                selected = next(
                    (url for item, url in matches if lead_key and re.sub(r"[^0-9a-z가-힣]+", "", item["title"].casefold()) == lead_key),
                    matches[0][1],
                )
                artist_album_links += 1
                if apply:
                    db.execute(
                        text("update public.artist_albums set youtube_url=:url, updated_at=now() where id=:id and youtube_url is null"),
                        {"id": album_id, "url": selected},
                    )
            if apply:
                db.commit()
            linked_tracks += artist_links
            linked_albums += artist_album_links
            per_artist.append((artist["name_ko"] or artist["name"], artist_links, artist_album_links, len(videos)))
    return linked_tracks, linked_albums, per_artist


def looks_like_photo(candidate: dict) -> bool:
    searchable = unquote(" ".join(str(candidate.get(key) or "") for key in (
        "image_url", "original_image_url", "source_url",
    ))).lower().replace(" ", "_")
    return not any(marker in searchable for marker in NON_PHOTO_MARKERS)


def publishable_photo(item: dict) -> bool:
    return (
        item.get("decision") == "photo_candidate"
        and item.get("category") in {"photoshoot", "activity_photo"}
        and item.get("people_visible") is True
        and item.get("promotional_layout") is False
        and float(item.get("confidence") or 0) >= 0.85
        and item.get("source_provider") == "wikimedia_commons"
        and all(item.get(field) for field in (
            "creator_name", "license_name", "license_url", "source_url", "image_url",
        ))
        and looks_like_photo(item)
    )


def backfill_gallery(db, settings, apply: bool, target: int = 4):
    artists = db.execute(text("""
        select id, slug, name, name_ko
        from public.artists
        where active = true
        order by id
    """)).mappings().all()
    total_added = 0
    per_artist = []
    for artist in artists:
        current = db.execute(text("""
            select count(*)
            from public.artist_gallery_items
            where artist_id=:artist_id and active=true and review_status='approved'
              and creator_name is not null and license_name is not null
              and license_url is not null and source_page_url is not null
        """), {"artist_id": artist["id"]}).scalar_one()
        deficit = max(0, target - current)
        if not deficit:
            per_artist.append((artist["name_ko"] or artist["name"], current, 0, 0, 0, "complete"))
            continue
        existing = set(db.execute(text(
            "select image_url from public.artist_gallery_items where artist_id=:artist_id"
        ), {"artist_id": artist["id"]}).scalars())
        qid = re.search(r"-q(\d+)$", artist["slug"])
        logs: list[str] = []
        candidates = collect_commons_candidates(f"Q{qid.group(1)}" if qid else None, 20, logs)
        fresh = [candidate for candidate in candidates if candidate["image_url"] not in existing and looks_like_photo(candidate)]
        fresh = fresh[: min(8, max(deficit * 3, deficit))]
        report = classify_gallery(
            {"gallery_limit": len(fresh)}, [], settings, logs, extra_candidates=fresh
        ) if fresh else {"items": []}
        selected = [item for item in report.get("items", []) if publishable_photo(item)][:deficit]
        for index, item in enumerate(selected, start=current + 1):
            if apply:
                db.execute(text("""
                    insert into public.artist_gallery_items
                      (artist_id,title,image_url,active,display_order,source_page_url,original_image_url,
                       source_collected_at,source_provider,creator_name,license_name,license_url,
                       attribution_text,rights_verified_at,ai_decision,ai_reason,ai_confidence,
                       ai_category,ai_people_visible,ai_promotional_layout,review_status,updated_at)
                    values
                      (:artist_id,:title,:image_url,true,:display_order,:source_page_url,:original_image_url,
                       :source_collected_at,'wikimedia_commons',:creator_name,:license_name,:license_url,
                       :attribution_text,now(),:ai_decision,:ai_reason,:ai_confidence,
                       :ai_category,:ai_people_visible,:ai_promotional_layout,'approved',now())
                    on conflict do nothing
                """), {
                    "artist_id": artist["id"], "title": f"공식 라이선스 활동 사진 {index}",
                    "image_url": item["image_url"], "display_order": index,
                    "source_page_url": item["source_url"],
                    "original_image_url": item.get("original_image_url") or item["image_url"],
                    "source_collected_at": item.get("source_collected_at"),
                    "creator_name": item["creator_name"], "license_name": item["license_name"],
                    "license_url": item["license_url"], "attribution_text": item.get("attribution_text"),
                    "ai_decision": item["decision"], "ai_reason": item.get("reason"),
                    "ai_confidence": item.get("confidence"), "ai_category": item.get("category"),
                    "ai_people_visible": item.get("people_visible"),
                    "ai_promotional_layout": item.get("promotional_layout"),
                })
        if apply:
            db.commit()
        total_added += len(selected)
        verdicts = Counter(str(item.get("decision") or "missing") for item in report.get("items", []))
        per_artist.append((
            artist["name_ko"] or artist["name"], current, len(candidates), len(fresh), len(selected),
            ",".join(f"{key}:{value}" for key, value in sorted(verdicts.items())) or "none",
        ))
    return total_added, per_artist


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Commit eligible updates")
    parser.add_argument("--youtube", action="store_true")
    parser.add_argument("--gallery", action="store_true")
    parser.add_argument("--gallery-target", type=int, default=4)
    args = parser.parse_args()
    if not args.youtube and not args.gallery:
        args.youtube = args.gallery = True
    settings = get_settings()
    with SessionLocal() as db:
        if args.youtube:
            tracks, albums, details = backfill_youtube(db, settings, args.apply)
            print(f"youtube tracks={tracks} albums={albums} apply={args.apply}")
            for detail in details:
                print("youtube_artist", *detail)
        if args.gallery:
            added, details = backfill_gallery(db, settings, args.apply, args.gallery_target)
            print(f"gallery added={added} target={args.gallery_target} apply={args.apply}")
            for detail in details:
                print("gallery_artist", *detail)


if __name__ == "__main__":
    main()
