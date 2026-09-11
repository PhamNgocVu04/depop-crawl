import os, imaplib, email, re, requests
from email.header import decode_header

ICLOUD_USER = os.environ["ICLOUD_USER"]
ICLOUD_PASS = os.environ["ICLOUD_PASS"]
WEBAPP_URL  = os.environ["WEBAPP_URL"]
SECRET      = os.environ["SECRET"]
LIMIT       = 30

SHOP_ACC = {"488663384":"PTT1","468105245":"DT262","419902926":"DNE123"}
DEFAULT_ACC = "ICLOUD"

def m1(p, s, f=re.I):
    m = re.search(p, s, f)
    return m.group(1) if m else ""

def resolve_label(url):
    if not url: return ""
    cur = url
    try:
        for _ in range(10):
            r = requests.get(cur, allow_redirects=False, timeout=15)
            if 300 <= r.status_code < 400:
                cur = r.headers.get("Location", "")
                if not cur: break
                if re.search(r"goshippo\.com|\.pdf", cur, re.I): return cur
            else:
                break
    except:
        return url
    return cur

def get_parts(msg):
    html = text = ""
    if msg.is_multipart():
        for p in msg.walk():
            ct = p.get_content_type()
            if ct == "text/html" and not html:
                html = p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "ignore")
            elif ct == "text/plain" and not text:
                text = p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "ignore")
    else:
        text = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "ignore")
    return html, text

def subj(msg):
    out = ""
    for b, enc in decode_header(msg.get("Subject", "")):
        out += b.decode(enc or "utf-8", "ignore") if isinstance(b, bytes) else b
    return out

M = imaplib.IMAP4_SSL("imap.mail.me.com", 993)
M.login(ICLOUD_USER, ICLOUD_PASS)
M.select("INBOX")
typ, data = M.search(None, 'UNSEEN', 'SUBJECT', 'shipping')
ids = data[0].split()[-LIMIT:] if data[0] else []
rows = []

for i in reversed(ids):
    typ, d = M.fetch(i, '(BODY.PEEK[])')
    msg = email.message_from_bytes(d[0][1])
    s = subj(msg)
    if "shipping label and sale confirmation" not in s.lower():
        continue
    html, text = get_parts(msg)
    shop = m1(r"media-photos\.depop\.com/b1/(\d+)/", html)
    acc = SHOP_ACC.get(shop, DEFAULT_ACC)
    name = re.sub(r"\.+$", "", m1(r"for\s+@([A-Za-z0-9_.\-]+)", s))
    if not name:
        cand = m1(r"Buyer\s+\S+\s+([A-Za-z0-9_.\-]{2,40})", text)
        name = "" if cand.lower() in ("profile", "view") else cand
    date = msg.get("Date", "")
    label = m1(r'<a\b[^>]*?href="([^"]+)"[^>]*>(?:(?!</a>|<a\b)[\s\S])*?Download shipping label', html)
    label = resolve_label(label.replace("&amp;", "&"))
    receive = m1(r"What you.ll receive[\s\S]*?\$?([\d,]+\.\d{2})", text)
    oi, si = text.find("Order details"), text.find("Ship to")
    region = text[oi:si] if (oi >= 0 and si > oi) else text
    items = re.findall(r"image\s+[\s\S]+?\s+Size:\s*([A-Za-z0-9]+)\s+\$[\d.,]+", region, re.I)
    imgs = []
    for u in re.findall(r"https://media-photos\.depop\.com/[^\s\"'#=]+\.jpg", html, re.I):
        if u not in imgs: imgs.append(u)
    if not items:
        size = m1(r"Size:\s*([A-Za-z0-9]+)", text)
        rows.append([acc, date, name, size, imgs[0] if imgs else "", label, f"${receive}" if receive else ""])
    else:
        for k, sz in enumerate(items):
            rows.append([acc, date, name, sz, imgs[k] if k < len(imgs) else "", label,
                         (f"${receive}" if receive else "") if k == 0 else ""])
    M.store(i, '+FLAGS', '\\Seen')

if rows:
    r = requests.post(WEBAPP_URL, json={"secret": SECRET, "rows": rows}, timeout=30)
    print("Sheet:", r.text)
print(f"Đã xử {len(rows)} dòng")
M.logout()