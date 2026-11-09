#!/usr/bin/env python3
"""Loopback-only read-only UI. Nginx must authenticate all external requests."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>服务状态</title><style>
body{font:16px system-ui;max-width:880px;margin:45px auto;padding:0 24px;background:#f5f6f8;color:#20252c}
h1{font-size:28px}section{background:white;border-radius:12px;padding:20px;margin:16px 0}
.bad{color:#a12424}.good{color:#166539}pre{white-space:pre-wrap;line-height:1.8}small{color:#555}
dialog{border:0;border-radius:12px;max-width:520px;padding:24px}button{padding:9px 18px;cursor:pointer}
</style><h1>服务状态</h1><p>仅管理员可见 · 每 30 秒刷新</p>
<section><h2 id="title">正在检查</h2><div id="alerts"></div><small id="updated"></small></section>
<section><h2>运行概况</h2><pre id="details"></pre></section>
<small>页面关闭或网站无法访问时不能弹窗。监听正常不代表大陆线路或 Netflix 播放可用。
备份只在 VPS；请定期通过 SSH/SFTP 下载到 Mac。</small>
<dialog id="notice"><h2>服务提醒</h2><p id="noticeText"></p><button id="dismiss">知道了</button></dialog>
<script>
let previous = new Set();
const el = id => document.getElementById(id);
el('dismiss').onclick = () => el('notice').close();
async function refresh(){
 try{
  const response=await fetch('./api/status',{cache:'no-store',credentials:'same-origin'});
  if(!response.ok)throw Error();const s=await response.json();
  const stale=Date.now()-Date.parse(s.updated_at)>180000;
  const alerts=[...s.alerts];if(stale)alerts.push({id:'stale',text:'状态采集超过 3 分钟未更新。'});
  el('title').textContent=alerts.length?'有待处理提醒':'当前检查正常';
  el('title').className=alerts.length?'bad':'good';
  el('alerts').replaceChildren(...alerts.map(a=>{let p=document.createElement('p');p.textContent=a.text;return p}));
  el('updated').textContent='采集时间：'+new Date(s.updated_at).toLocaleString();
  const backup=s.backup?.generated_at?new Date(s.backup.generated_at).toLocaleString():'暂无';
  el('details').textContent='最近成功备份：'+backup+'\\n证书到期：'+(s.certificate_expiry?new Date(s.certificate_expiry*1000).toLocaleString():'未知')+
   '\\n容器运行：'+(s.container_running?'正常':'异常')+'\\n面板 / 订阅 / 代理监听：'+
   Object.values(s.ports).map(v=>v?'正常':'异常').join(' / ')+'\\n磁盘可用：'+(s.disk_free_bytes/1073741824).toFixed(1)+' GiB';
  const fresh=alerts.filter(a=>!previous.has(a.id));previous=new Set(alerts.map(a=>a.id));
  if(fresh.length){el('noticeText').textContent=fresh.map(a=>a.text).join('\\n');if(!el('notice').open)el('notice').showModal();}
 }catch(e){el('title').textContent='无法获取服务状态';el('title').className='bad';}
}
refresh();setInterval(refresh,30000);
</script></html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/', '/index.html'):
            body, mime = PAGE.encode(), 'text/html; charset=utf-8'
        elif self.path == '/api/status':
            try:
                body = Path('/var/lib/panel-monitor/status.json').read_bytes()
            except OSError:
                self.send_error(503)
                return
            mime = 'application/json; charset=utf-8'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 9100), Handler).serve_forever()
