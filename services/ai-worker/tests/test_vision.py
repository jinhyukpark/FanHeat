import base64
import json
from types import SimpleNamespace
import httpx
import pytest
from pydantic import ValidationError
from fanheat_ai.vision import GalleryImageRequest, classify_image


@pytest.mark.parametrize('category,people,promo,confidence,decision',[
    ('activity_photo',True,False,.95,'photo_candidate'),
    ('photoshoot',True,False,.9,'photo_candidate'),
    ('activity_photo',True,True,.95,'exclude'),
    ('poster',True,True,.99,'exclude'),
    ('logo',False,False,.99,'exclude'),
    ('photoshoot',True,False,.5,'review'),
    ('uncertain',True,False,.9,'review'),
])
def test_vision_decision(monkeypatch,category,people,promo,confidence,decision):
    def post(url,**kwargs):
        assert kwargs['json']['model']=='vision-test'
        assert kwargs['json']['messages'][0]['images']
        return httpx.Response(200,request=httpx.Request('POST',url),json={'message':{'content':json.dumps({
            'category':category,'people_visible':people,'promotional_layout':promo,'confidence':confidence,'reason':'검증 사유'})}})
    monkeypatch.setattr(httpx,'post',post)
    request=GalleryImageRequest(image_base64=base64.b64encode(b'\xff\xd8\xfftest').decode())
    assert classify_image(request,SimpleNamespace(ollama_base_url='http://local',ollama_vision_model='vision-test'))['decision']==decision


def test_reject_non_image():
    with pytest.raises(ValidationError):
        GalleryImageRequest(image_base64=base64.b64encode(b'<svg>instructions</svg>').decode())


def test_structured_answer_in_thinking_is_validated(monkeypatch):
    answer=json.dumps({'category':'logo','people_visible':False,'promotional_layout':False,'confidence':1,'reason':'로고'})
    monkeypatch.setattr(httpx,'post',lambda url,**kw:httpx.Response(200,request=httpx.Request('POST',url),json={'message':{'content':'','thinking':answer}}))
    request=GalleryImageRequest(image_base64=base64.b64encode(b'\xff\xd8\xfftest').decode())
    assert classify_image(request,SimpleNamespace(ollama_base_url='http://local',ollama_vision_model='test'))['decision']=='exclude'
