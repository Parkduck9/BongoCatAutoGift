"""One live cat table. OCR and mouse actions use current observations."""
from dataclasses import dataclass, field
import threading
import time
import unicodedata
import vision
from clicker import ClickAborted

@dataclass
class Cat:
    id: int
    observation: vision.Observation
    ocr_name: str
    score: float
    manual_name: str = ''
    enabled: bool = False
    chat_read: bool = False
    chat_until: float = 0
    handled: set = field(default_factory=set)
    pending: dict = field(default_factory=dict)
    @property
    def name(self):
        return self.manual_name or self.ocr_name or '이름 미확인'

def supported(text):
    letters=[c for c in text if unicodedata.category(c).startswith('L')]
    return bool(letters) and all(('a'<=c.lower()<='z') or ('가'<=c<='힣') or ('\u1100'<=c<='\u11ff') or ('\u3130'<=c<='\u318f') for c in letters)

def position(ob):
    return ob.box.x,ob.box.y,ob.box.w,ob.box.h

class Session:
    def __init__(self, db, scanner=vision.scan, name_reader=vision.read_name, chat_reader=vision.read_chat, clock=time.time):
        self.db,self.scanner,self.name_reader,self.chat_reader,self.clock=db,scanner,name_reader,chat_reader,clock
        self.cats={}
        self.next_id=1
        self.lock=threading.RLock()
        self.notices=[]
    def snapshot(self):
        with self.lock:
            return [dict(id=c.id,name=c.name,enabled=c.enabled,score=c.score,x=c.observation.touch[0],y=c.observation.touch[1],gifts=list(c.observation.gifts)) for c in self.cats.values()]
    def edit(self,cat_id,name,enabled):
        with self.lock:
            c=self.cats[cat_id]
            c.manual_name=name.strip() if name.strip()!=c.ocr_name else ''
            c.enabled=bool(enabled)
    def observe(self,frame):
        observations=self.scanner(frame)
        with self.lock:
            old=list(self.cats.values())
        same={position(c.observation):c for c in old}
        fresh=[(ob,*self.name_reader(frame,ob)) for ob in observations if position(ob) not in same]
        remaining=[c for c in old if position(c.observation) not in {position(ob) for ob in observations}]
        table={}
        with self.lock:
            events=self.notices
            self.notices=[]
        for ob in observations:
            c=same.get(position(ob))
            if c is None:
                _,name,score=next(row for row in fresh if row[0] is ob)
                candidates=[c for c in remaining if name and c.ocr_name==name]
                unique=sum(row[1]==name for row in fresh)==1 and sum(c.ocr_name==name for c in old)==1
                if unique and len(candidates)==1:
                    c=candidates[0]
                else:
                    c=Cat(self.next_id,ob,name,score)
                    self.next_id+=1
            c.observation=ob
            c.handled.intersection_update(ob.gifts)
            for side,(due,point,name) in list(c.pending.items()):
                if self.clock()>=due:
                    result='clicked_ok' if position(ob)==point and side not in ob.gifts else 'clicked_no_change' if position(ob)==point else 'unverified'
                    self.db.add_gift(self.clock(),name,side,result)
                    events.append(f'{name} {side}: '+{'clicked_ok':'선물 아이콘 사라짐 확인','clicked_no_change':'클릭 후 아이콘 변화 없음','unverified':'위치 변경으로 결과 확인 불가'}[result])
                    del c.pending[side]
            table[c.id]=c
        for c in old:
            if c.id not in table:
                for side,(_,_,name) in c.pending.items():
                    self.db.add_gift(self.clock(),name,side,'unverified')
                    events.append(f'{name} {side}: 퇴장으로 결과 확인 불가')
        with self.lock:
            self.cats=table
        for c in table.values():
            bubble=c.observation.bubble
            if bubble is None:
                c.chat_read=False
            elif not c.chat_read and self.clock()>=c.chat_until:
                c.chat_read=True
                c.chat_until=self.clock()+3
                try:
                    text,score=self.chat_reader(frame,bubble)
                    status='recognized' if score>=.8 else 'estimated'
                    if not text.strip():
                        text,score,status='채팅 로그 기록에 실패했습니다.',0,'failed'
                    elif not supported(text):
                        continue
                except Exception:
                    text,score,status='채팅 로그 기록에 실패했습니다.',0,'failed'
                self.db.add_chat(self.clock(),c.name,text,cat_id=c.id,status=status,score=score)
                events.append(f'{c.name}: {text} ({status})')
        return events
    def _fresh(self,cat_id,frame):
        with self.lock:
            c=self.cats.get(cat_id)
            point=position(c.observation) if c else None
        if c is None:
            return None,None
        matches=[ob for ob in self.scanner(frame) if position(ob)==point]
        return (c,matches[0]) if len(matches)==1 else (None,None)
    def touch(self,cat_id,frame,clicker,monitor,should_stop=lambda:False):
        c,ob=self._fresh(cat_id,frame)
        if c is None or should_stop():
            return False
        try:
            clicker.click(monitor['left']+ob.touch[0],monitor['top']+ob.touch[1],abort=should_stop)
        except ClickAborted:
            return False
        return True
    def send_gift(self,cat_id,side,frame,clicker,monitor,should_stop=lambda:False,dry_run=False):
        c,ob=self._fresh(cat_id,frame)
        if c is None or not c.enabled or side not in ob.gifts or side in c.handled or should_stop():
            return False
        name,score=self.name_reader(frame,ob)
        if not name or (score<.5 and not c.manual_name) or name not in {c.ocr_name,c.manual_name}:
            with self.lock:
                c.enabled=False
                self.notices.append(f'{c.name}: 새 화면에서 이름 재확인 실패, 선물 체크 해제')
            return False
        with self.lock:
            if not c.enabled or should_stop():
                return False
            if not dry_run:
                x,y=ob.gifts[side].c
                try:
                    clicker.click(monitor['left']+x,monitor['top']+y,abort=should_stop)
                except ClickAborted:
                    return False
                c.pending[side]=(self.clock()+1.5,position(ob),c.name)
            c.handled.add(side)
            self.db.add_gift(self.clock(),c.name,side,'dry_run' if dry_run else 'clicked_sent')
        return True
