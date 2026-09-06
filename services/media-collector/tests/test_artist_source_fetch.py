import httpx
import pytest

from media_collector import artist_import


def mock_sources(monkeypatch, handler):
    client = httpx.Client
    monkeypatch.setattr(artist_import.httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(artist_import.socket, "getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("8.8.8.8", 443))])


def test_http_redirect_is_retried_only_over_https(monkeypatch):
    visited = []
    def handler(request):
        visited.append(str(request.url))
        if request.url.path == "/":
            return httpx.Response(302, headers={"location": "http://official.example/profile"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<title>Artist</title>")
    mock_sources(monkeypatch, handler)
    logs = []
    pages = artist_import.collect_artist_sources(["https://official.example/"], logs=logs)
    assert visited == ["https://official.example/", "https://official.example/profile"]
    assert pages[0]["title"] == "Artist"
    assert any("HTTPS" in log for log in logs)


def test_blocked_source_does_not_discard_successful_source(monkeypatch):
    def handler(request):
        if request.url.host == "blocked.example":
            return httpx.Response(403)
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<title>Artist</title>")
    mock_sources(monkeypatch, handler)
    logs = []
    pages = artist_import.collect_artist_sources(["https://blocked.example", "https://official.example"], logs=logs)
    assert len(pages) == 1
    assert any("HTTP 403" in log for log in logs)


@pytest.mark.parametrize("location", ["http://127.0.0.1/private", "https://127.0.0.1/private", "file:///etc/passwd"])
def test_unsafe_redirects_are_never_fetched(monkeypatch, location):
    visited = []
    def handler(request):
        visited.append(str(request.url))
        return httpx.Response(302, headers={"location": location})
    mock_sources(monkeypatch, handler)
    monkeypatch.setattr(artist_import.socket, "getaddrinfo", lambda host, *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1" if host == "127.0.0.1" else "8.8.8.8", 443))])
    with pytest.raises(ValueError, match="수집 가능한 공식 출처가 없습니다"):
        artist_import.collect_artist_sources(["https://official.example"])
    assert len(visited) == 1


def test_no_sources_does_not_create_empty_artist():
    with pytest.raises(ValueError, match="수집 가능한 공식 출처가 없습니다"):
        artist_import.collect_artist_sources([])
