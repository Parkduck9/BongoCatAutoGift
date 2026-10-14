"""Single-window controller; only one worker captures and clicks."""
import datetime
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog
import capture
import clicker
import config
from session import Session
from store import Store

class Runner:
    def __init__(self, cfg, db, events):
        self.cfg,self.events=cfg,events
        self.session=Session(db)
        self._stop=threading.Event()
        self._thread=None
        self.touches=queue.Queue()
        self.last_dry=True
    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())
    def should_stop(self):
        if clicker.stop_pressed():
            self._stop.set()
        return self._stop.is_set()
    def stop(self):
        self._stop.set()
    def start(self, mode='run', cat_id=None):
        if self.running:
            if mode=='touch':
                self.touches.put(cat_id)
            return
        self._stop.clear()
        self._thread=threading.Thread(target=self._loop,args=(mode,cat_id),daemon=True)
        self._thread.start()
    def _loop(self,mode,cat_id):
        cap=None
        try:
            cap=capture.Capturer()
            monitor=self.cfg['monitor']
            mon=cap.monitor(monitor)
            mouse=clicker.Clicker()
            if mode=='touch':
                done=self.session.touch(cat_id,cap.grab(monitor),mouse,mon,self.should_stop)
                self.events.put(('log','터치 1회 완료' if done else '위치가 바뀌었거나 정지되어 터치하지 않았습니다.'))
                return
            while not self.should_stop():
                frame=cap.grab(monitor)
                for event in self.session.observe(frame):
                    self.events.put(('log',event))
                self.events.put(('rows',self.session.snapshot()))
                if mode=='scan':
                    break
                while not self.touches.empty() and not self.should_stop():
                    target=self.touches.get_nowait()
                    done=self.session.touch(target,cap.grab(monitor),mouse,mon,self.should_stop)
                    self.events.put(('log','터치 1회 완료' if done else '위치 변경: 터치 취소'))
                for row in self.session.snapshot():
                    if row['enabled']:
                        for side in row['gifts']:
                            if self.should_stop():
                                break
                            sent=self.session.send_gift(row['id'],side,cap.grab(monitor),mouse,mon,self.should_stop,self.cfg['dry_run'])
                            if sent:
                                self.events.put(('log',f"{row['name']} {side}: {'연습 기록' if self.cfg['dry_run'] else '선물 클릭 보냄'}"))
                if self._stop.wait(.25):
                    break
        except Exception as exc:
            self.events.put(('error',str(exc)))
        finally:
            while not self.touches.empty():
                self.touches.get_nowait()
            if cap:
                cap.close()
            self.events.put(('rows',self.session.snapshot()))
            self.events.put(('stopped',None))

class App:
    def __init__(self,root):
        self.root=root
        root.title('Bongo Helper — 고양이 목록')
        root.geometry('920x700')
        self.cfg=config.load()
        self.db=Store(config.BASE_DIR/'data'/'bongo.db')
        self.events=queue.Queue()
        self.runner=Runner(self.cfg,self.db,self.events)
        self.closing=False
        self.rows={}
        cap=capture.Capturer()
        try:
            monitors=cap.monitors()[1:]
        finally:
            cap.close()
        top=ttk.Frame(root,padding=10);top.pack(fill='x')
        ttk.Label(top,text='게임 모니터').pack(side='left')
        self.monitor=tk.StringVar(value=str(self.cfg['monitor']))
        self.monbox=ttk.Combobox(top,textvariable=self.monitor,values=[str(i) for i in range(1,len(monitors)+1)],width=4,state='readonly')
        self.monbox.pack(side='left',padx=6)
        self.monbox.bind('<<ComboboxSelected>>',self.change_monitor)
        self.dry=tk.BooleanVar(value=True)
        self.drybox=ttk.Checkbutton(top,text='연습 모드 (선물 클릭 안 함)',variable=self.dry)
        self.drybox.pack(side='left',padx=8)
        self.scanbutton=ttk.Button(top,text='화면 파악',command=lambda:self.start('scan'));self.scanbutton.pack(side='left',padx=3)
        self.startbutton=ttk.Button(top,text='시작',command=lambda:self.start('run'));self.startbutton.pack(side='left',padx=3)
        ttk.Button(top,text='정지 (F12)',command=self.runner.stop).pack(side='left',padx=3)
        self.status=tk.StringVar(value='모니터를 선택하고 화면 파악을 누르세요. 선물은 체크한 고양이에게만 보냅니다.')
        ttk.Label(root,textvariable=self.status,wraplength=880,padding=10).pack(fill='x')
        self.table=ttk.Treeview(root,columns=('check','name','score','position','gifts'),show='headings',height=11,selectmode='browse')
        for key,title,width in [('check','선물',60),('name','이름',240),('score','인식',80),('position','터치 위치',150),('gifts','선물 위치',180)]:
            self.table.heading(key,text=title);self.table.column(key,width=width)
        self.table.pack(fill='both',expand=True,padx=10)
        self.table.bind('<<TreeviewSelect>>',self.select)
        self.table.bind('<Button-1>',self.toggle)
        edit=ttk.Frame(root,padding=10);edit.pack(fill='x')
        self.name=tk.StringVar();ttk.Entry(edit,textvariable=self.name,width=28).pack(side='left')
        self.checked=tk.BooleanVar()
        ttk.Checkbutton(edit,text='선물 보내기',variable=self.checked).pack(side='left',padx=6)
        ttk.Button(edit,text='이름·체크 저장',command=self.save_cat).pack(side='left',padx=4)
        ttk.Button(edit,text='선택한 고양이 실제 터치 1회',command=self.touch).pack(side='left',padx=8)
        tabs=ttk.Notebook(root);tabs.pack(fill='both',expand=True,padx=10,pady=5)
        self.log=tk.Text(tabs,height=7,state='disabled',wrap='word');tabs.add(self.log,text='동작 기록')
        chatframe=ttk.Frame(tabs);tabs.add(chatframe,text='채팅 기록')
        toolbar=ttk.Frame(chatframe);toolbar.pack(fill='x')
        ttk.Button(toolbar,text='새로고침',command=self.refresh_chat).pack(side='left')
        ttk.Button(toolbar,text='채팅 내보내기',command=self.export_chat).pack(side='left',padx=5)
        self.chat=ttk.Treeview(chatframe,columns=('time','name','status','text'),show='headings',height=7)
        for key,title,width in [('time','시간',150),('name','이름',150),('status','판독',65),('text','문장',440)]:
            self.chat.heading(key,text=title);self.chat.column(key,width=width)
        self.chat.pack(fill='both',expand=True)
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh_chat();root.after(100,self.poll)
    def change_monitor(self,event=None):
        if self.runner.running:
            return
        self.cfg['monitor']=int(self.monitor.get())
        self.runner.session=Session(self.db)
        self.show_rows([])
        config.save(self.cfg)
    def start(self,mode):
        if self.runner.running:
            return
        self.cfg['monitor']=int(self.monitor.get())
        self.cfg['dry_run']=self.dry.get()
        if mode=='run' and self.runner.last_dry!=self.cfg['dry_run']:
            for c in self.runner.session.cats.values():
                c.handled.clear()
        if mode=='run':
            self.runner.last_dry=self.cfg['dry_run']
        config.save(self.cfg)
        self.monbox.configure(state='disabled');self.drybox.configure(state='disabled')
        self.scanbutton.configure(state='disabled');self.startbutton.configure(state='disabled')
        self.status.set('화면을 확인하고 있습니다…' if mode=='scan' else '실행 중 · F12로 정지')
        self.runner.start(mode)
    def selected(self):
        selection=self.table.selection()
        return int(selection[0]) if selection else None
    def select(self,event=None):
        row=self.rows.get(self.selected())
        if row:
            self.name.set('' if row['name']=='이름 미확인' else row['name']);self.checked.set(row['enabled'])
    def save_cat(self):
        target=self.selected()
        if target is None:
            self.status.set('목록에서 고양이를 먼저 선택하세요.');return
        try:
            self.runner.session.edit(target,self.name.get(),self.checked.get())
        except KeyError:
            self.status.set('이 고양이는 화면에서 사라졌습니다.');return
        self.show_rows(self.runner.session.snapshot());self.status.set('이름과 선물 체크를 저장했습니다.')
    def toggle(self,event):
        item=self.table.identify_row(event.y)
        if item and self.table.identify_column(event.x)=='#1':
            row=self.rows[int(item)]
            self.runner.session.edit(int(item),'' if row['name']=='이름 미확인' else row['name'],not row['enabled'])
            self.show_rows(self.runner.session.snapshot())
    def touch(self):
        target=self.selected()
        if target is None:
            self.status.set('터치할 고양이를 먼저 선택하세요.');return
        if not self.runner.running:
            self.monbox.configure(state='disabled');self.drybox.configure(state='disabled')
            self.scanbutton.configure(state='disabled');self.startbutton.configure(state='disabled')
        self.runner.start('touch',target)
    def show_rows(self,rows):
        selected=self.selected()
        self.rows={row['id']:row for row in rows}
        for item in self.table.get_children():
            if int(item) not in self.rows:
                self.table.delete(item)
        for row in rows:
            values=('☑' if row['enabled'] else '☐',row['name'],f"{row['score']:.0%}",f"{row['x']}, {row['y']}",', '.join('왼쪽' if side=='left' else '오른쪽' for side in row['gifts']))
            item=str(row['id'])
            if self.table.exists(item):self.table.item(item,values=values)
            else:self.table.insert('', 'end', iid=item,values=values)
    def refresh_chat(self):
        self.chat.delete(*self.chat.get_children())
        for index,row in enumerate(self.db.query_chat_records()[-1000:]):
            status={'recognized':'인식','estimated':'추정','failed':'실패'}[row['status']]
            self.chat.insert('','end',values=(datetime.datetime.fromtimestamp(row['ts']).strftime('%m-%d %H:%M:%S'),row['speaker'],status,row['text']))
    def export_chat(self):
        path=filedialog.asksaveasfilename(defaultextension='.txt',filetypes=[('텍스트','*.txt')])
        if path:
            from pathlib import Path
            rows=self.db.query_chat_records()
            Path(path).write_text('\n'.join(f"{datetime.datetime.fromtimestamp(r['ts'])} [{r['status']}] {r['speaker']}: {r['text']}" for r in rows),encoding='utf-8')
            self.status.set('채팅 기록을 내보냈습니다.')
    def poll(self):
        while not self.events.empty():
            kind,value=self.events.get_nowait()
            if kind=='rows':self.show_rows(value)
            elif kind in ('log','error'):
                self.log.configure(state='normal');self.log.insert('end',value+'\n');self.log.see('end');self.log.configure(state='disabled')
                if kind=='error':self.status.set('오류: '+value)
                self.refresh_chat()
            elif kind=='stopped':
                self.monbox.configure(state='readonly');self.drybox.configure(state='normal')
                self.scanbutton.configure(state='normal');self.startbutton.configure(state='normal')
                if not self.status.get().startswith('오류:'):
                    self.status.set(f'화면 파악 완료: {len(self.rows)}마리 · 이름을 수정하고 선물 대상을 체크하세요.')
        if self.closing and not self.runner.running:
            self.db.close();self.root.destroy();return
        self.root.after(100,self.poll)
    def close(self):
        self.closing=True;self.runner.stop()
        self.status.set('작업을 정지하고 닫는 중…')

def main():
    capture.set_dpi_aware()
    root=tk.Tk();App(root);root.mainloop()
