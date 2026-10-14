from pathlib import Path
import cv2
import numpy as np
import pytest
import vision
from session import supported

FIXTURES=Path(__file__).parent/'fixtures'

def test_reference_gift_cat_and_exact_icon_coordinates():
    frame=cv2.imread(str(FIXTURES/'gift_cat.png'))
    observations=vision.scan(frame)
    assert len(observations)==1
    ob=observations[0]
    assert ob.gifts['left'].c==(55,93)
    assert ob.gifts['right'].c==(166,94)
    assert vision.read_name(frame,ob)[0]=='Alucard'
    assert ob.bubble is None

def test_reference_numeric_cat_is_kept_and_bubble_assigned():
    frame=cv2.imread(str(FIXTURES/'chat_cat.png'))
    observations=vision.scan(frame)
    assert len(observations)==1
    ob=observations[0]
    assert ob.counter and vision.read_name(frame,ob)==('',0)
    assert ob.bubble is not None
    text,score=vision.read_chat(frame,ob.bubble)
    assert text and supported(text) and score>0

@pytest.mark.parametrize('scale',[1.25,1.5])
def test_scaled_gift_reference(scale):
    frame=cv2.imread(str(FIXTURES/'gift_cat.png'))
    frame=cv2.resize(frame,None,fx=scale,fy=scale)
    observations=vision.scan(frame)
    assert len(observations)==1 and len(observations[0].gifts)==2

def test_full_monitor_with_both_reference_cats():
    canvas=np.full((1080,1920,3),[30,30,30],np.uint8)
    for filename,x,y in [('gift_cat.png',100,100),('chat_cat.png',1100,500)]:
        image=cv2.imread(str(FIXTURES/filename))
        h,w=image.shape[:2];canvas[y:y+h,x:x+w]=image
    obs=vision.scan(canvas)
    assert len(obs)==2 and obs[1].bubble is not None
    assert obs[0].gifts['left'].c==(155,193)

def test_adjacent_nameplates_are_not_counter_menus():
    canvas=np.full((200,400,3),[30,30,30],np.uint8)
    canvas[120:140,50:150]=[233,224,216]
    canvas[120:140,155:255]=[233,224,216]
    obs=vision.scan(canvas)
    assert len(obs)==2 and not any(ob.counter for ob in obs)
@pytest.mark.parametrize('sentence',['Hello world','안녕하세요'])
def test_actual_english_and_korean_chat_ocr(sentence):
    from test_ocr import render
    from detect import Box
    frame=render(sentence)
    h,w=frame.shape[:2]
    text,score=vision.read_chat(frame,Box(0,0,w,h))
    assert text.replace(' ','')==sentence.replace(' ','') and score>=.8
