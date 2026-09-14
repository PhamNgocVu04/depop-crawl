import os, imaplib, email, re, requests
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import timezone, timedelta

ICLOUDS = [
    {"user": os.environ["ICLOUD_USER"],  "pw": os.environ["ICLOUD_PASS"]},
    {"user": os.environ["ICLOUD_USER2"], "pw": os.environ["ICLOUD_PASS2"]},
    {"user": os.environ["ICLOUD_USER3"], "pw": os.environ["ICLOUD_PASS3"]},
]
WEBAPP_URL = os.environ["WEBAPP_URL"]
SECRET     = os.environ["SECRET"]
LIMIT      = 30

SHOP_ACC = {"488663384":"PTT1","468105245":"DT262","419902926":"DNE123","351098196":"TN11","353275642":"Fdx 40","307831158":"TN2"}
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

def process_icloud(user, pw):
    rows = []
    M = imaplib.IMAP4_SSL("imap.mail.me.com", 993)
    M.login(user, pw)
    M.select("INBOX")
    typ, data = M.search(None, 'UNSEEN', 'SUBJECT', 'shipping')
    ids = data[0].split()[-LIMIT:] if data[0] else []
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
        ts = 0
        try:
            dt = parsedate_to_datetime(date).astimezone(timezone(timedelta(hours=7)))
            date = f"{dt.day}/{dt.month}"
            ts = dt.timestamp()
        except:
            pass
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
            rows.append({"ts": ts, "date": date, "acc": acc, "name": name, "size": size,
                         "img": imgs[0] if imgs else "",
                         "label": label, "earning": f"${receive}" if receive else ""})
        else:
            for k, sz in enumerate(items):
                rows.append({"ts": ts, "date": date, "acc": acc, "name": name, "size": sz,
                             "img": imgs[k] if k < len(imgs) else "",
                             "label": label,
                             "earning": (f"${receive}" if receive else "") if k == 0 else ""})
        M.store(i, '+FLAGS', '\\Seen')
    M.logout()
    return rows

all_rows = []
for a in ICLOUDS:
    try:
        all_rows += process_icloud(a["user"], a["pw"])
    except Exception as e:
        print("Loi acc", a["user"], ":", e)

# Sắp xếp cũ -> mới (đơn mới xuống dưới cùng)
all_rows.sort(key=lambda r: r.get("ts", 0))

if all_rows:
    r = requests.post(WEBAPP_URL, json={"secret": SECRET, "rows": all_rows}, timeout=30)
    print("Sheet:", r.text)
print(f"Da xu {len(all_rows)} dong")
