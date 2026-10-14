"""Full-monitor geometry, independent of user calibration."""
from dataclasses import dataclass
from functools import lru_cache
import cv2
import numpy as np
import config
import ocr
from capture import crop
from detect import Box, find_templates

@dataclass
class Observation:
    box: Box
    touch: tuple
    gifts: dict
    bubble: Box | None
    counter: bool

@lru_cache(maxsize=1)
def templates():
    images = [cv2.imread(str(config.RESOURCE_DIR / 'assets' / f'gift_{side}.png')) for side in ('left', 'right')]
    if any(image is None for image in images):
        raise FileNotFoundError('선물 기준 이미지가 없습니다.')
    return images

def scan(frame):
    b, g, r = cv2.split(frame.astype(np.int16))
    mask = (((abs(b-233)<13) & (abs(g-224)<13) & (abs(r-216)<13) & (b-g>=4) & (g-r>=4)).astype(np.uint8)*255)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    components=[cv2.boundingRect(contour) for contour in contours]
    observations = []
    for contour in contours:
        x,y,w,h = cv2.boundingRect(contour)
        if not (12<=h<=60 and 28<=w<=500 and 1.25<=w/h<=18):
            continue
        if np.count_nonzero(mask[y:y+h,x:x+w])/(w*h)<.65:
            continue
        box = Box(max(0,x-2), max(0,y-2), w+4,h+4)
        # A counter has a small separate menu immediately to its right.
        counter = any(0<=mx-(x+w)<=h*.7 and abs(my-y)<4 and
                      8<=mw<=h*1.5 and abs(mh-h)<5
                      for mx,my,mw,mh in components)
        touch = (box.c[0]+(round(h*.5) if counter else 0), max(0,box.y-round(box.h*.85)))
        gifts = {}
        if not counter:
            for side, sign in [('left',-1),('right',1)]:
                cx = box.c[0]+round(sign*55*box.h/24)
                cy = box.y-round(21*box.h/24)
                radius = round(box.h*.9)
                x0,y0=max(0,cx-radius),max(0,cy-radius)
                roi=frame[y0:min(frame.shape[0],cy+radius),x0:min(frame.shape[1],cx+radius)]
                size=max(12,round(box.h))
                # Interpolated label borders lose pixels at desktop scaling. Match
                # icon sizes locally instead of treating label height as exact.
                sizes=sorted({max(12,round(size*ratio)) for ratio in (.9,1,1.1,1.2,1.3)})
                refs=[cv2.resize(t,(s,s)) for t in templates() for s in sizes]
                hits=find_templates(roi,refs,.90,scale=1,offset=(x0,y0)) if roi.size else []
                if hits:
                    hit=max(hits,key=lambda hit:hit.score)
                    gifts[side]=Box(hit.x,hit.y,hit.w,hit.h)
        observations.append(Observation(box,touch,gifts,None,counter))
    # A shared icon between adjacent cats cannot establish ownership.
    ambiguous=set()
    for i,a in enumerate(observations):
        for j,b in enumerate(observations[i+1:],i+1):
            for sa,ga in a.gifts.items():
                for sb,gb in b.gifts.items():
                    if abs(ga.c[0]-gb.c[0])<min(ga.w,gb.w)/2 and abs(ga.c[1]-gb.c[1])<min(ga.h,gb.h)/2:
                        ambiguous.update(((i,sa),(j,sb)))
    for index,side in ambiguous:
        del observations[index].gifts[side]
    white=cv2.inRange(frame,np.array([235,235,235],np.uint8),np.array([255,255,255],np.uint8))
    contours,_=cv2.findContours(white,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    candidates=[]
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour)
        if 45<=w<=600 and 14<=h<=90 and w/h>=1.5 and cv2.contourArea(contour)/(w*h)>.70:
            candidates.append(Box(x,y,w,h))
    for bubble in sorted(candidates,key=lambda v:v.w*v.h):
        owners=[]
        for index,ob in enumerate(observations):
            dx=abs(bubble.x+bubble.w-(ob.touch[0]-10*ob.box.h/24))
            dy=abs(bubble.y+bubble.h-(ob.touch[1]-35*ob.box.h/24))
            if dx<ob.box.h*1.3 and dy<ob.box.h:
                owners.append(index)
        if len(owners)==1 and observations[owners[0]].bubble is None:
            observations[owners[0]].bubble=bubble
    return sorted(observations,key=lambda ob:(ob.box.y,ob.box.x))

def read_name(frame, observation):
    box=observation.box
    text,score=ocr.recognize(crop(frame,(box.x+3,box.y+3,box.w-6,box.h-6)))
    return ('',0) if observation.counter or ocr.is_numeric(text) else (text,score)

def read_chat(frame, box):
    return ocr.recognize(crop(frame,(box.x+2,box.y+2,box.w-4,box.h-4)))
