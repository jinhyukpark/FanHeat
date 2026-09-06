from media_collector import commons_gallery


def meta(value):
    return {"value": value}


def test_commons_accepts_attribution_license_and_builds_credit(monkeypatch):
    def api(url, params):
        if params["action"] == "wbgetentities":
            return {"entities":{"Q1":{"claims":{"P373":[{"mainsnak":{"datavalue":{"value":"IVE (group)"}}}]},"sitelinks":{}}}}
        if params.get("list") == "categorymembers":
            return {"query":{"categorymembers":[{"title":"File:IVE.jpg","ns":6}]}}
        return {"query":{"pages":[{"title":"File:IVE.jpg","imageinfo":[{
            "url":"https://upload.wikimedia.org/original.jpg", "thumburl":"https://upload.wikimedia.org/thumb.jpg",
            "descriptionurl":"https://commons.wikimedia.org/wiki/File:IVE.jpg",
            "extmetadata":{"LicenseShortName":meta("CC BY-SA 4.0"),
                "LicenseUrl":meta("https://creativecommons.org/licenses/by-sa/4.0/"),
                "Artist":meta('<a href="/wiki/User:Photographer">Photographer</a>')},
        }]}]}}
    monkeypatch.setattr(commons_gallery, "_api", api)
    logs = []
    result = commons_gallery.collect_commons_candidates("Q1", 10, logs)
    assert len(result) == 1
    assert result[0]["creator_name"] == "Photographer"
    assert result[0]["source_provider"] == "wikimedia_commons"
    assert result[0]["attribution_text"] == "Photographer · CC BY-SA 4.0 · Wikimedia Commons"


def test_commons_traverses_bounded_artist_subcategories(monkeypatch):
    calls = []
    def api(url, params):
        if params["action"] == "wbgetentities":
            return {"entities":{"Q3":{"claims":{"P373":[{"mainsnak":{"datavalue":{"value":"Artist"}}}]},"sitelinks":{}}}}
        if params.get("list") == "categorymembers":
            calls.append(params["cmtitle"])
            if params["cmtitle"] == "Category:Artist":
                return {"query":{"categorymembers":[{"title":"Category:Artist in 2026","ns":14}]}}
            return {"query":{"categorymembers":[{"title":"File:Event.jpg","ns":6}]}}
        return {"query":{"pages":[{"title":"File:Event.jpg","imageinfo":[{"url":"https://upload.wikimedia.org/event.jpg",
          "descriptionurl":"https://commons.wikimedia.org/wiki/File:Event.jpg","extmetadata":{
          "LicenseShortName":meta("CC BY 4.0"),"LicenseUrl":meta("https://creativecommons.org/licenses/by/4.0/"),"Artist":meta("Fan photographer")}}]}]}}
    monkeypatch.setattr(commons_gallery, "_api", api)
    assert len(commons_gallery.collect_commons_candidates("Q3", 5, [])) == 1
    assert calls == ["Category:Artist", "Category:Artist in 2026"]


def test_commons_rejects_missing_creator_and_noncommercial_license(monkeypatch):
    monkeypatch.setattr(commons_gallery, "_api", lambda url, params: (
        {"entities":{"Q2":{"claims":{"P18":[{"mainsnak":{"datavalue":{"value":"No.jpg"}}}]},"sitelinks":{}}}}
        if params["action"] == "wbgetentities" else
        {"query":{"pages":[{"title":"File:No.jpg","imageinfo":[{"url":"https://upload.wikimedia.org/no.jpg",
         "extmetadata":{"LicenseShortName":meta("CC BY-NC 4.0"),"Artist":meta("")}}]}]}}
    ))
    assert commons_gallery.collect_commons_candidates("Q2", 10, []) == []
