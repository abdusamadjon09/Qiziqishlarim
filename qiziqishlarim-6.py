from flask import Flask,request,redirect,url_for,session,render_template_string,flash
import sqlite3,os,re,json,urllib.request,urllib.error
from functools import wraps
from werkzeug.security import generate_password_hash,check_password_hash
from werkzeug.utils import secure_filename

app=Flask(__name__)
app.secret_key='qiziqishlarim-pro-v3-secret'
BASE=os.path.dirname(os.path.abspath(__file__))
DB=os.path.join(BASE,'qiziqishlarim.db')
UPLOAD=os.path.join(BASE,'static','uploads')
os.makedirs(UPLOAD,exist_ok=True)
app.config['MAX_CONTENT_LENGTH']=4*1024*1024

# =========================================================
# AI USTOZ SOZLAMALARI
# =========================================================
AI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")
AI_KEY_FILE = os.path.join(BASE, "ai_key.txt")
AI_API_URL = "https://api.openai.com/v1/responses"

def get_ai_key():
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(AI_KEY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""

def ai_request(prompt, interest="", mode="answer"):
    key = get_ai_key()
    if not key:
        return None, "AI kaliti topilmadi. Pydroid 3 papkasiga ai_key.txt fayl yarating va ichiga OpenAI API kalitingizni yozing."

    safe_interest = (interest or "aniqlanmagan")[:300]
    mode_text = {
        "answer": "Savolga tushunarli va aniq javob ber. Kerak bo'lsa misol keltir.",
        "learn": "Avval mavzuni sodda tushuntir, keyin bosqichma-bosqich o'rgat, amaliy mashq ber va oxirida 3 ta tekshiruv savoli ber.",
        "quiz": "Mavzu bo'yicha 5 ta savol tuz. Javoblarni darhol bermagin; foydalanuvchi javob bergach tekshir.",
        "plan": "Foydalanuvchiga shu qiziqishni o'rganish uchun 7 kunlik, kunma-kun qisqa reja tuz."
    }.get(mode, "Savolga foydali javob ber.")

    system = (
        "Sen Qiziqishlarim platformasining AI Ustozisan. "
        "Foydalanuvchi o'quvchi bo'lishi mumkin, shuning uchun javoblar xavfsiz, "
        "yoshga mos, hurmatli va tushunarli bo'lsin. "
        "Foydalanuvchining shaxsiy ma'lumotlarini so'rama va oshkor qilma. "
        "Asosiy maqsad: foydalanuvchining qiziqishini o'rgatish va amaliy yordam berish. "
        "Javobni o'zbek tilida ber, agar foydalanuvchi boshqa tilni ishlatsa, o'sha tilga moslash. "
        "Qiziqish: " + safe_interest + ". " + mode_text
    )

    payload = {
        "model": AI_MODEL,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system}]},
            {"role": "user", "content": [{"type": "input_text", "text": prompt[:12000]}]}
        ]
    }

    req = urllib.request.Request(
        AI_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))

        # Responses API normally exposes output_text in SDKs; the raw HTTP
        # response contains output items, so support both forms.
        text = data.get("output_text")
        if not text:
            chunks = []
            for item in data.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") in ("output_text", "text"):
                        if content.get("text"):
                            chunks.append(content["text"])
            text = "\n".join(chunks).strip()

        if not text:
            return None, "AI javob qaytarmadi."
        return text, None

    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="ignore")
        except Exception:
            detail = str(e)
        return None, "AI API xatosi: HTTP " + str(e.code) + ". " + detail[:500]
    except Exception as e:
        return None, "AI bilan bog'lanishda xato: " + str(e)[:400]

REGIONS={
'Andijon viloyati':['Andijon shahri','Asaka','Andijon tumani','Baliqchi','Buloqboshi','Izboskan','Jalaquduq','Marhamat','Paxtaobod','Shahrixon','Xojaobod'],
'Buxoro viloyati':['Buxoro shahri','Buxoro tumani','Gijduvon','Jondor','Kogon','Olot','Peshku','Qorakol','Romitan','Shofirkon'],
'Fargona viloyati':['Fargona shahri','Rishton','Qoqon','Margilon','Oltiariq','Bagdod','Beshariq','Dangara','Furqat','Quva','Quvasoy','Sox','Toshloq','Uchkoprik'],
'Jizzax viloyati':['Jizzax shahri','Arnasoy','Baxmal','Dostlik','Forish','Gallaorol','Mirzachol','Paxtakor','Zomin','Zarbdor'],
'Namangan viloyati':['Namangan shahri','Chortoq','Chust','Kosonsoy','Mingbuloq','Norin','Pop','Toraqorgon','Uchqorgon','Uychi','Yangiqorgon'],
'Navoiy viloyati':['Navoiy shahri','Konimex','Karmana','Qiziltepa','Navbahor','Nurota','Tomdi','Uchquduq','Xatirchi'],
'Qashqadaryo viloyati':['Qarshi shahri','Chiroqchi','Dehqonobod','Guzor','Kasbi','Kitob','Koson','Mirishkor','Muborak','Nishon','Qamashi','Shahrisabz','Yakkabog'],
'Samarqand viloyati':['Samarqand shahri','Bulungur','Ishtixon','Jomboy','Kattaqorgon','Narpay','Nurobod','Oqdaryo','Paxtachi','Payariq','Pastdargom','Qoshrabot','Toyloq','Urgut'],
'Sirdaryo viloyati':['Guliston shahri','Boyovut','Guliston tumani','Mirzaobod','Oqoltin','Sayxunobod','Sardoba','Sirdaryo tumani','Xovos'],
'Surxondaryo viloyati':['Termiz shahri','Angor','Bandixon','Boysun','Denov','Jarquorgon','Muzrabot','Oltinsoy','Qiziriq','Qumqorgon','Sariosiyo','Sherobod','Shorchi','Uzun'],
'Toshkent viloyati':['Nurafshon','Angren','Bekobod','Boka','Chinoz','Ohangaron','Olmaliq','Oqqorgon','Parkent','Piskent','Quyi Chirchiq','Toshkent tumani','Yangiyol','Zangiota'],
'Toshkent shahri':['Chilonzor','Yunusobod','Mirzo Ulugbek','Sergeli','Shayxontohur','Yakkasaroy','Mirobod','Olmazor','Uchtepa','Bektemir','Yashnobod','Yangihayot'],
'Xorazm viloyati':['Urganch shahri','Bogot','Gurlan','Hazorasp','Xiva','Xonqa','Qoshkopir','Shovot','Urganch tumani','Yangiariq','Yangibozor'],
'Qoraqalpogiston Respublikasi':['Nukus shahri','Amudaryo','Beruniy','Chimboy','Ellikqala','Kegeyli','Moynoq','Qanlikol','Qongirot','Shumanay','Taxtakopir','Tortkol','Xojayli']}
CLASSES=[f'{i}-sinf' for i in range(5,12)]

def con():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c

def init():
 c=con()
 c.execute('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE,password TEXT,first_name TEXT,last_name TEXT,region TEXT DEFAULT '',district TEXT DEFAULT '',school TEXT DEFAULT '',class_name TEXT DEFAULT '',interests TEXT DEFAULT '',bio TEXT DEFAULT '',photo TEXT DEFAULT '',is_admin INTEGER DEFAULT 0,is_active INTEGER DEFAULT 1,created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
 c.execute('''CREATE TABLE IF NOT EXISTS favorites(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,target_id INTEGER,UNIQUE(user_id,target_id))''')
 c.execute('''CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,title TEXT,message TEXT,is_read INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
 c.execute('''CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,content TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
 c.execute('''CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY AUTOINCREMENT,reporter_id INTEGER,target_id INTEGER,reason TEXT,status TEXT DEFAULT 'Yangi',created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
 c.execute('''CREATE TABLE IF NOT EXISTS groups_(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,description TEXT,keyword TEXT)''')
 c.execute('''CREATE TABLE IF NOT EXISTS members(id INTEGER PRIMARY KEY AUTOINCREMENT,group_id INTEGER,user_id INTEGER,UNIQUE(group_id,user_id))''')
 c.execute('''CREATE TABLE IF NOT EXISTS ai_messages(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,role TEXT,message TEXT,interest TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
 if not c.execute('SELECT id FROM users WHERE username=?',('admin',)).fetchone(): c.execute('INSERT INTO users(username,password,first_name,last_name,is_admin) VALUES(?,?,?,?,1)',('admin',generate_password_hash('12345'),'Administrator','PRO'))
 if c.execute('SELECT COUNT(*) n FROM groups_').fetchone()['n']==0:
  c.executemany('INSERT INTO groups_(name,description,keyword) VALUES(?,?,?)',[(a,b,k) for a,b,k in [('IT va Dasturlash','Python, web va dasturlash','python'),('Kiber xavfsizlik','Kiberxavfsizlik','kiber'),('Sport','Sportga qiziqadiganlar','sport'),('Kitobxonlar','Kitob va adabiyot','kitob'),('Dizayn va ijod','Rasm, dizayn, video','dizayn'),('Tillar','Ingliz tili va boshqa tillar','ingliz'),('Biznes','Tadbirkorlik','biznes')]])
 c.commit();c.close()
init()

def user():
 if not session.get('uid'): return None
 c=con();u=c.execute('SELECT * FROM users WHERE id=? AND is_active=1',(session['uid'],)).fetchone();c.close();return u

def login_req(f):
 @wraps(f)
 def w(*a,**k):
  if not user(): flash('Avval tizimga kiring.','warning');return redirect(url_for('login'))
  return f(*a,**k)
 return w

def admin_req(f):
 @wraps(f)
 def w(*a,**k):
  u=user()
  if not u or not u['is_admin']: flash('Faqat admin uchun.','danger');return redirect(url_for('home'))
  return f(*a,**k)
 return w

def sim(a,b):
 clean=lambda x:set(z for z in re.split(r'[,\s]+',re.sub(r'[^\w\s,]',' ',(x or '').lower())) if len(z)>=3)
 x,y=clean(a),clean(b)
 return round(len(x&y)/len(x|y)*100) if x and y else 0

def layout(title,body,**kw):
 u=user();n=0
 if u:
  c=con();n=c.execute('SELECT COUNT(*) n FROM notifications WHERE user_id=? AND is_read=0',(u['id'],)).fetchone()['n'];c.close()
 return render_template_string(BASE,title=title,body=render_template_string(body,user=u,regions=REGIONS,classes=CLASSES,**kw),user=u,n=n)

BASE='''<!doctype html><html lang="uz"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{title}} | Qiziqishlarim PRO</title><style>*{box-sizing:border-box}body{margin:0;background:#07111f;color:#e5e7eb;font-family:Arial}.nav{background:#0b1728;padding:12px;border-bottom:1px solid #26384f;position:sticky;top:0;z-index:5}.navin{max-width:1200px;margin:auto;display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}.logo{font-size:21px;font-weight:bold;color:#38bdf8}.links{display:flex;gap:5px;flex-wrap:wrap}.links a{padding:8px;border-radius:9px}.links a:hover{background:#1e293b}.container{width:94%;max-width:1200px;margin:22px auto 60px}.hero,.card{background:#0d1a2b;border:1px solid #26384f;border-radius:18px;padding:18px;box-shadow:0 10px 30px #0004}.hero{padding:28px 20px}.hero h1{font-size:clamp(28px,6vw,50px);margin:0 0 10px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}input,select,textarea{width:100%;padding:12px;margin:5px 0 12px;background:#050c16;color:#fff;border:1px solid #3a506a;border-radius:10px}textarea{min-height:130px}label{font-weight:bold}.btn{display:inline-block;background:#2563eb;color:#fff;padding:10px 13px;border-radius:10px;margin:3px;font-weight:bold;border:0}.green{background:#059669}.red{background:#dc2626}.gray{background:#475569}.purple{background:#7c3aed}.muted{color:#94a3b8}.small{font-size:13px}.center{text-align:center}.flash{background:#17263b;border:1px solid #3a506a;padding:12px;border-radius:10px;margin-bottom:10px}.profile{display:flex;gap:12px;align-items:center}.avatar{width:75px;height:75px;border-radius:50%;object-fit:cover;background:#1e293b;border:2px solid #38bdf8}.big{width:130px;height:130px}.badge{display:inline-block;background:#26384f;padding:5px 8px;border-radius:8px;font-size:12px}.stat{font-size:32px;font-weight:bold;color:#38bdf8}.progress{height:8px;background:#26384f;border-radius:99px;overflow:hidden}.progress div{height:100%;background:#38bdf8}.wrap{overflow:auto}table{width:100%;border-collapse:collapse}th,td{padding:8px;border-bottom:1px solid #26384f;text-align:left}@media(max-width:800px){.grid,.grid2{grid-template-columns:1fr 1fr}}@media(max-width:560px){.grid,.grid2{grid-template-columns:1fr}.links{width:100%}}</style></head><body><nav class="nav"><div class="navin"><a class="logo" href="{{url_for('home')}}">Qiziqishlarim PRO</a><div class="links"><a href="{{url_for('home')}}">🏠</a><a href="{{url_for('students')}}">🔎 O'quvchilar</a><a href="{{url_for('school_groups')}}">🏫 Maktab guruhlari</a><a href="{{url_for('groups')}}">👥 Guruhlar</a><a href="{{url_for('ai_mentor')}}">🤖 AI Ustoz</a>{% if user %}<a href="{{url_for('dashboard')}}">📊 Kabinet</a><a href="{{url_for('similar')}}">✨ Moslar</a><a href="{{url_for('favorites')}}">⭐</a><a href="{{url_for('notifications')}}">🔔 {{n}}</a><a href="{{url_for('profile',user_id=user['id'])}}">👤 Profil</a>{% if user['is_admin'] %}<a href="{{url_for('admin')}}">⚙️ Admin</a>{% endif %}<a href="{{url_for('logout')}}">🚪</a>{% else %}<a href="{{url_for('login')}}">🔐 Kirish</a><a href="{{url_for('register')}}">📝 Ro'yxat</a>{% endif %}</div></div></nav><main class="container">{% with m=get_flashed_messages(with_categories=true) %}{% for cat,msg in m %}<div class="flash">{{msg}}</div>{% endfor %}{% endwith %}{{body|safe}}</main><div class="center muted" style="padding:30px">Qiziqishlarim PRO AI © 2026</div></body></html>'''

@app.route('/')
def home():
 c=con();total=c.execute('SELECT COUNT(*) n FROM users WHERE is_admin=0 AND is_active=1').fetchone()['n'];regs=c.execute('SELECT COUNT(DISTINCT region) n FROM users WHERE is_admin=0 AND is_active=1 AND region!=""').fetchone()['n'];gs=c.execute('SELECT COUNT(*) n FROM groups_').fetchone()['n'];latest=c.execute('SELECT * FROM users WHERE is_admin=0 AND is_active=1 ORDER BY id DESC LIMIT 6').fetchall();anns=c.execute('SELECT * FROM announcements ORDER BY id DESC LIMIT 4').fetchall();c.close()
 body='''<section class="hero"><h1>Qiziqishlarim PRO 🚀</h1><p class="muted">O'quvchilar qiziqishlarini yozadi va o'xshash qiziqishdagi o'quvchilarni topadi.</p>{% if user %}<a class="btn" href="{{url_for('similar')}}">✨ Menga moslar</a><a class="btn green" href="{{url_for('edit')}}">✏️ Profil</a>{% else %}<a class="btn" href="{{url_for('register')}}">📝 Boshlash</a>{% endif %}</section><br><div class="grid"><div class="card"><div class="stat">{{total}}</div>O'quvchilar</div><div class="card"><div class="stat">{{regs}}</div>Hududlar</div><div class="card"><div class="stat">{{gs}}</div>Guruhlar</div></div><br><div class="card"><h2>🆕 Yangi o'quvchilar</h2><div class="grid">{% for u in latest %}<div class="card"><h3>{{u['first_name']}} {{u['last_name']}}</h3><p class="muted">{{u['region']}} / {{u['district']}}</p><p>{{(u['interests'] or '—')[:130]}}</p><a class="btn" href="{{url_for('profile',user_id=u['id'])}}">Profil</a></div>{% else %}<p>Hali o'quvchi yo'q.</p>{% endfor %}</div></div>{% if anns %}<br><div class="card"><h2>📢 E'lonlar</h2>{% for a in anns %}<div class="card"><h3>{{a['title']}}</h3><p>{{a['content']}}</p></div>{% endfor %}</div>{% endif %}'''
 return layout('Bosh sahifa',body,total=total,regs=regs,gs=gs,latest=latest,anns=anns)

@app.route('/register',methods=['GET','POST'])
def register():
 if request.method=='POST':
  f=request.form;vals=[f.get('username','').strip(),f.get('password',''),f.get('first_name','').strip(),f.get('last_name','').strip(),f.get('region',''),f.get('district','').strip(),f.get('school','').strip(),f.get('class_name',''),f.get('interests','').strip()]
  if not all(vals[:4]): flash('Ism, familiya, login va parol majburiy.','danger');return redirect(url_for('register'))
  c=con()
  if c.execute('SELECT id FROM users WHERE username=?',(vals[0],)).fetchone(): c.close();flash('Bu login mavjud.','danger');return redirect(url_for('register'))
  cur=c.execute('INSERT INTO users(username,password,first_name,last_name,region,district,school,class_name,interests) VALUES(?,?,?,?,?,?,?,?,?)',(vals[0],generate_password_hash(vals[1]),*vals[2:]));uid=cur.lastrowid;c.commit();c.close();session['uid']=uid;return redirect(url_for('profile',user_id=uid))
 body='''<div class="grid2"><div class="hero"><h1>📝 Ro'yxatdan o'tish</h1><p class="muted">Profil yarating.</p></div><div class="card"><form method="post"><label>Ism *</label><input name="first_name" required><label>Familiya *</label><input name="last_name" required><label>Login *</label><input name="username" required><label>Parol *</label><input type="password" name="password" required><label>Viloyat</label><select name="region"><option value="">Tanlang</option>{% for r in regions %}<option>{{r}}</option>{% endfor %}</select><label>Tuman</label><input name="district"><label>Maktab</label><input name="school"><label>Sinf</label><select name="class_name"><option value="">Tanlang</option>{% for x in classes %}<option>{{x}}</option>{% endfor %}</select><label>Mening qiziqishlarim</label><textarea name="interests" placeholder="Python, futbol, kitob, ingliz tili..."></textarea><button class="btn">📝 Ro'yxatdan o'tish</button></form></div></div>'''
 return layout("Ro'yxatdan o'tish",body)

@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  c=con();u=c.execute('SELECT * FROM users WHERE username=?',(request.form.get('username','').strip(),)).fetchone();c.close()
  if u and u['is_active'] and check_password_hash(u['password'],request.form.get('password','')): session['uid']=u['id'];return redirect(url_for('home'))
  flash("Login yoki parol noto'g'ri.",'danger')
 body='''<div style="max-width:500px;margin:auto"><div class="card"><h1>🔐 Kirish</h1><form method="post"><label>Login</label><input name="username" required><label>Parol</label><input type="password" name="password" required><button class="btn">Kirish</button></form></div></div>''';return layout('Kirish',body)

@app.route('/logout')
def logout(): session.clear();return redirect(url_for('home'))

@app.route('/profile/<int:user_id>')
def profile(user_id):
 c=con();u=c.execute('SELECT * FROM users WHERE id=? AND is_active=1',(user_id,)).fetchone();c.close()
 if not u: flash('Profil topilmadi.','danger');return redirect(url_for('students'))
 body='''<div class="grid2"><div class="card center">{% if target['photo'] %}<img class="avatar big" src="{{url_for('static',filename='uploads/'+target['photo'])}}">{% else %}<div class="avatar big" style="display:inline-block;padding-top:45px">👤</div>{% endif %}<h1>{{target['first_name']}} {{target['last_name']}}</h1><p class="muted">@{{target['username']}}</p>{% if user and user['id']==target['id'] %}<a class="btn green" href="{{url_for('edit')}}">✏️ Tahrirlash</a>{% endif %}</div><div class="card"><h2>📚 Ma'lumotlar</h2><p>📍 {{target['region']}} / {{target['district']}}</p><p>🏫 {{target['school']}} | {{target['class_name']}}</p><h3>✨ Mening qiziqishlarim</h3><div class="card">{{target['interests'] or 'Qiziqishlar yozilmagan.'}}</div>{% if target['bio'] %}<h3>📝 Men haqimda</h3><div class="card">{{target['bio']}}</div>{% endif %}{% if user and user['id']!=target['id'] %}<a class="btn" href="{{url_for('favorite',user_id=target['id'])}}">⭐ Saqlash</a><a class="btn red" href="{{url_for('report',user_id=target['id'])}}">🚩 Shikoyat</a>{% endif %}</div></div>''';return layout('Profil',body,target=u)

@app.route('/edit',methods=['GET','POST'])
@login_req
def edit():
 u=user()
 if request.method=='POST':
  f=request.form;photo=u['photo'];p=request.files.get('photo')
  if p and p.filename:
   if '.' not in p.filename or p.filename.rsplit('.',1)[1].lower() not in {'jpg','jpeg','png','webp'}: flash("Rasm formati noto'g'ri.",'danger');return redirect(url_for('edit'))
   ext=secure_filename(p.filename).rsplit('.',1)[1].lower();photo=f"u{u['id']}_{int(__import__('time').time())}.{ext}";p.save(os.path.join(UPLOAD,photo))
  c=con();c.execute('UPDATE users SET first_name=?,last_name=?,region=?,district=?,school=?,class_name=?,interests=?,bio=?,photo=? WHERE id=?',(f.get('first_name',''),f.get('last_name',''),f.get('region',''),f.get('district',''),f.get('school',''),f.get('class_name',''),f.get('interests',''),f.get('bio',''),photo,u['id']));c.commit();c.close();flash('Profil saqlandi.','success');return redirect(url_for('profile',user_id=u['id']))
 body='''<div class="card"><h1>✏️ Profilni tahrirlash</h1><form method="post" enctype="multipart/form-data"><div class="grid2"><div><label>Ism</label><input name="first_name" value="{{user['first_name']}}"><label>Familiya</label><input name="last_name" value="{{user['last_name']}}"><label>Viloyat</label><select name="region"><option value="">Tanlang</option>{% for r in regions %}<option {% if r==user['region'] %}selected{% endif %}>{{r}}</option>{% endfor %}</select><label>Tuman</label><input name="district" value="{{user['district']}}"><label>Maktab</label><input name="school" value="{{user['school']}}"><label>Sinf</label><select name="class_name"><option value="">Tanlang</option>{% for x in classes %}<option {% if x==user['class_name'] %}selected{% endif %}>{{x}}</option>{% endfor %}</select></div><div><label>Mening qiziqishlarim</label><textarea name="interests">{{user['interests']}}</textarea><label>Men haqimda</label><textarea name="bio">{{user['bio']}}</textarea><label>Profil rasmi</label><input type="file" name="photo" accept=".jpg,.jpeg,.png,.webp"><button class="btn green">💾 Saqlash</button></div></div></form></div>''';return layout('Profilni tahrirlash',body)

@app.route('/students')
def students():
 q=request.args.get('q','').strip();r=request.args.get('region','');d=request.args.get('district','');s=request.args.get('school','');cl=request.args.get('class_name','');sql='SELECT * FROM users WHERE is_admin=0 AND is_active=1';pa=[]
 if q: sql+=' AND (first_name LIKE ? OR last_name LIKE ? OR interests LIKE ? OR school LIKE ?)';pa += ['%'+q+'%']*4
 if r: sql+=' AND region=?';pa.append(r)
 if d: sql+=' AND district LIKE ?';pa.append('%'+d+'%')
 if s: sql+=' AND school LIKE ?';pa.append('%'+s+'%')
 if cl: sql+=' AND class_name=?';pa.append(cl)
 sql+=' ORDER BY id DESC LIMIT 150';c=con();rows=c.execute(sql,pa).fetchall();c.close()
 body='''<div class="card"><h1>🔎 O'quvchilar</h1><form><div class="grid2"><div><label>Qidiruv</label><input name="q" value="{{q}}" placeholder="Ism, maktab, qiziqish"><label>Viloyat</label><select name="region"><option value="">Barchasi</option>{% for r in regions %}<option {% if r==region %}selected{% endif %}>{{r}}</option>{% endfor %}</select><label>Tuman</label><input name="district" value="{{district}}"></div><div><label>Maktab</label><input name="school" value="{{school}}"><label>Sinf</label><select name="class_name"><option value="">Barchasi</option>{% for x in classes %}<option {% if x==cl %}selected{% endif %}>{{x}}</option>{% endfor %}</select><button class="btn">🔎 Qidirish</button></div></div></form></div><br><div class="card"><h2>Natijalar: {{rows|length}}</h2><div class="grid">{% for u in rows %}<div class="card"><h3>{{u['first_name']}} {{u['last_name']}}</h3><p class="muted">{{u['region']}} / {{u['district']}}</p><p>{{(u['interests'] or '—')[:150]}}</p><a class="btn" href="{{url_for('profile',user_id=u['id'])}}">Profil</a></div>{% else %}<p>Topilmadi.</p>{% endfor %}</div></div>''';return layout("O'quvchilar",body,rows=rows,q=q,region=r,district=d,school=s,cl=cl)

@app.route('/similar')
@login_req
def similar_page():
 u=user();c=con();allusers=c.execute('SELECT * FROM users WHERE id!=? AND is_admin=0 AND is_active=1',(u['id'],)).fetchall();c.close();rows=[]
 for x in allusers:
  sc=sim(u['interests'],x['interests'])
  if u['region'] and u['region']==x['region']: sc=min(100,sc+5)
  if u['class_name'] and u['class_name']==x['class_name']: sc=min(100,sc+3)
  if sc: rows.append((sc,x))
 rows.sort(key=lambda z:z[0],reverse=True)
 body='''<div class="hero"><h1>✨ Sizga mos o'quvchilar</h1><p class="muted">Qiziqishlar bo'yicha avtomatik moslik.</p></div><br><div class="grid">{% for sc,u in rows %}<div class="card"><h3>{{u['first_name']}} {{u['last_name']}}</h3><span class="badge">{{sc}}% moslik</span><br><br><div class="progress"><div style="width:{{sc}}%"></div></div><p>{{u['interests']}}</p><a class="btn" href="{{url_for('profile',user_id=u['id'])}}">Profil</a></div>{% else %}<div class="card"><h2>Mos o'quvchi topilmadi.</h2><a class="btn green" href="{{url_for('edit')}}">Qiziqishlaringizni yozing</a></div>{% endfor %}</div>''';return layout('Mos oquvchilar',body,rows=rows)

@app.route('/favorite/<int:user_id>')
@login_req
def favorite(user_id):
 u=user();c=con();c.execute('INSERT OR IGNORE INTO favorites(user_id,target_id) VALUES(?,?)',(u['id'],user_id));c.commit();c.close();flash('Profil saqlandi.','success');return redirect(url_for('profile',user_id=user_id))

@app.route('/favorites')
@login_req
def favorites():
 u=user();c=con();rows=c.execute('SELECT u.* FROM users u JOIN favorites f ON u.id=f.target_id WHERE f.user_id=? AND u.is_active=1',(u['id'],)).fetchall();c.close();body='''<div class="card"><h1>⭐ Saqlanganlar</h1><div class="grid">{% for u in rows %}<div class="card"><h3>{{u['first_name']}} {{u['last_name']}}</h3><p>{{u['interests']}}</p><a class="btn" href="{{url_for('profile',user_id=u['id'])}}">Profil</a></div>{% else %}<p>Saqlanganlar yo'q.</p>{% endfor %}</div></div>''';return layout('Saqlanganlar',body,rows=rows)

@app.route('/groups')
def groups():
 c=con();rows=c.execute('SELECT g.*,COUNT(m.id) members FROM groups_ g LEFT JOIN members m ON g.id=m.group_id GROUP BY g.id').fetchall();c.close();body='''<div class="hero"><h1>👥 Qiziqish guruhlari</h1></div><br><div class="grid">{% for g in rows %}<div class="card"><h2>{{g['name']}}</h2><p>{{g['description']}}</p><span class="badge">{{g['members']}} a'zo</span><br><br><a class="btn" href="{{url_for('group',gid=g['id'])}}">Guruh</a></div>{% endfor %}</div>''';return layout('Guruhlar',body,rows=rows)

@app.route('/group/<int:gid>')
def group(gid):
 c=con();g=c.execute('SELECT * FROM groups_ WHERE id=?',(gid,)).fetchone();members=c.execute('SELECT u.* FROM users u JOIN members m ON u.id=m.user_id WHERE m.group_id=?',(gid,)).fetchall();u=user();joined=False
 if u: joined=c.execute('SELECT id FROM members WHERE group_id=? AND user_id=?',(gid,u['id'])).fetchone() is not None
 c.close()
 if not g:return redirect(url_for('groups'))
 body='''<div class="card"><h1>👥 {{g['name']}}</h1><p>{{g['description']}}</p>{% if user %}{% if joined %}<a class="btn gray" href="{{url_for('leave_group',gid=g['id'])}}">Chiqish</a>{% else %}<a class="btn green" href="{{url_for('join_group',gid=g['id'])}}">➕ Qo'shilish</a>{% endif %}{% endif %}</div><br><div class="card"><h2>A'zolar</h2><div class="grid">{% for x in members %}<div class="card"><b>{{x['first_name']}} {{x['last_name']}}</b></div>{% endfor %}</div></div>''';return layout(g['name'],body,g=g,members=members,joined=joined)

@app.route('/group/<int:gid>/join')
@login_req
def join_group(gid):
 c=con();c.execute('INSERT OR IGNORE INTO members(group_id,user_id) VALUES(?,?)',(gid,user()['id']));c.commit();c.close();return redirect(url_for('group',gid=gid))

@app.route('/group/<int:gid>/leave')
@login_req
def leave_group(gid):
 c=con();c.execute('DELETE FROM members WHERE group_id=? AND user_id=?',(gid,user()['id']));c.commit();c.close();return redirect(url_for('group',gid=gid))

@app.route('/notifications')
@login_req
def notifications():
 u=user();c=con();rows=c.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC',(u['id'],)).fetchall();c.execute('UPDATE notifications SET is_read=1 WHERE user_id=?',(u['id'],));c.commit();c.close();body='''<div class="card"><h1>🔔 Bildirishnomalar</h1>{% for n in rows %}<div class="card"><h3>{{n['title']}}</h3><p>{{n['message']}}</p></div>{% else %}<p>Bildirishnoma yo'q.</p>{% endfor %}</div>''';return layout('Bildirishnomalar',body,rows=rows)

@app.route('/report/<int:user_id>',methods=['GET','POST'])
@login_req
def report(user_id):
 if request.method=='POST':
  reason=request.form.get('reason','').strip();c=con();c.execute('INSERT INTO reports(reporter_id,target_id,reason) VALUES(?,?,?)',(user()['id'],user_id,reason));c.commit();c.close();flash('Shikoyat yuborildi.','success');return redirect(url_for('profile',user_id=user_id))
 c=con();target=c.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone();c.close();body='''<div style="max-width:600px;margin:auto"><div class="card"><h1>🚩 Shikoyat</h1><p>{{target['first_name']}} {{target['last_name']}}</p><form method="post"><textarea name="reason" required placeholder="Sabab..."></textarea><button class="btn red">Yuborish</button></form></div></div>''';return layout('Shikoyat',body,target=target)

@app.route('/admin')
@admin_req
def admin():
 c=con();total=c.execute('SELECT COUNT(*) n FROM users WHERE is_admin=0').fetchone()['n'];active=c.execute('SELECT COUNT(*) n FROM users WHERE is_admin=0 AND is_active=1').fetchone()['n'];blocked=total-active;reports=c.execute("SELECT COUNT(*) n FROM reports WHERE status='Yangi'").fetchone()['n'];groups=c.execute('SELECT COUNT(*) n FROM groups_').fetchone()['n'];stats=c.execute('SELECT region,COUNT(*) n FROM users WHERE is_admin=0 AND is_active=1 AND region!="" GROUP BY region ORDER BY n DESC').fetchall();c.close();body='''<div class="hero"><h1>⚙️ Admin panel</h1></div><br><div class="grid"><div class="card"><div class="stat">{{total}}</div>Jami</div><div class="card"><div class="stat">{{active}}</div>Faol</div><div class="card"><div class="stat">{{blocked}}</div>Blok</div><div class="card"><div class="stat">{{reports}}</div>Shikoyat</div><div class="card"><div class="stat">{{groups}}</div>Guruh</div></div><br><div class="grid2"><div class="card"><a class="btn" href="{{url_for('admin_users')}}">👥 O'quvchilar</a><a class="btn red" href="{{url_for('admin_reports')}}">🚩 Shikoyatlar</a><a class="btn purple" href="{{url_for('admin_ann')}}">📢 E'lonlar</a><a class="btn green" href="{{url_for('admin_groups')}}">👥 Guruhlar</a><a class="btn purple" href="{{url_for('admin_school_groups')}}">🏫 Maktab guruhlari</a></div><div class="card"><h2>📊 Hududlar</h2>{% for s in stats %}<p>{{s['region']}} — {{s['n']}}</p>{% endfor %}</div></div>''';return layout('Admin',body,total=total,active=active,blocked=blocked,reports=reports,groups=groups,stats=stats)

@app.route('/admin/users')
@admin_req
def admin_users():
 q=request.args.get('q','').strip();c=con();
 if q:
  p='%'+q+'%';rows=c.execute('SELECT * FROM users WHERE first_name LIKE ? OR last_name LIKE ? OR username LIKE ? OR school LIKE ? ORDER BY id DESC',(p,p,p,p)).fetchall()
 else: rows=c.execute('SELECT * FROM users ORDER BY id DESC LIMIT 300').fetchall()
 c.close();body='''<div class="card"><h1>👥 Foydalanuvchilar</h1><form><input name="q" value="{{q}}" placeholder="Qidirish"><button class="btn">🔎</button></form></div><br><div class="card wrap"><table><tr><th>ID</th><th>Ism</th><th>Login</th><th>Holat</th><th>Amal</th></tr>{% for x in rows %}<tr><td>{{x['id']}}</td><td>{{x['first_name']}} {{x['last_name']}}</td><td>{{x['username']}}</td><td>{{'Faol' if x['is_active'] else 'Blok'}}</td><td><a class="btn" href="{{url_for('profile',user_id=x['id'])}}">Ko'rish</a>{% if not x['is_admin'] %}<a class="btn red" href="{{url_for('block',uid=x['id'])}}">{% if x['is_active'] %}Blok{% else %}Ochish{% endif %}</a><a class="btn gray" href="{{url_for('delete_user',uid=x['id'])}}">O'chirish</a>{% endif %}</td></tr>{% endfor %}</table></div>''';return layout('Admin users',body,rows=rows,q=q)

@app.route('/admin/block/<int:uid>')
@admin_req
def block(uid):
 c=con();x=c.execute('SELECT is_active FROM users WHERE id=? AND is_admin=0',(uid,)).fetchone();
 if x:c.execute('UPDATE users SET is_active=? WHERE id=?',(0 if x['is_active'] else 1,uid));c.commit()
 c.close();return redirect(url_for('admin_users'))

@app.route('/admin/delete/<int:uid>')
@admin_req
def delete_user(uid):
 c=con();x=c.execute('SELECT is_admin FROM users WHERE id=?',(uid,)).fetchone()
 if x and not x['is_admin']:
  for t in ['favorites','notifications','members']: c.execute(f'DELETE FROM {t} WHERE user_id=?',(uid,))
  c.execute('DELETE FROM users WHERE id=?',(uid,));c.commit()
 c.close();return redirect(url_for('admin_users'))

@app.route('/admin/reports')
@admin_req
def admin_reports():
 c=con();rows=c.execute('''SELECT r.*,a.first_name rf,a.last_name rl,b.first_name tf,b.last_name tl FROM reports r LEFT JOIN users a ON a.id=r.reporter_id LEFT JOIN users b ON b.id=r.target_id ORDER BY r.id DESC''').fetchall();c.close();body='''<div class="card wrap"><h1>🚩 Shikoyatlar</h1><table><tr><th>ID</th><th>Kim</th><th>Kim haqida</th><th>Sabab</th><th>Status</th><th></th></tr>{% for r in rows %}<tr><td>{{r['id']}}</td><td>{{r['rf']}} {{r['rl']}}</td><td>{{r['tf']}} {{r['tl']}}</td><td>{{r['reason']}}</td><td>{{r['status']}}</td><td><a class="btn green" href="{{url_for('done_report',rid=r['id'])}}">✓</a></td></tr>{% endfor %}</table></div>''';return layout('Shikoyatlar',body,rows=rows)

@app.route('/admin/reports/done/<int:rid>')
@admin_req
def done_report(rid):
 c=con();c.execute("UPDATE reports SET status='Korib chiqildi' WHERE id=?",(rid,));c.commit();c.close();return redirect(url_for('admin_reports'))

@app.route('/admin/announcements',methods=['GET','POST'])
@admin_req
def admin_ann():
 c=con()
 if request.method=='POST':
  title=request.form.get('title','').strip();text=request.form.get('content','').strip()
  if title and text:
   c.execute('INSERT INTO announcements(title,content) VALUES(?,?)',(title,text));us=c.execute('SELECT id FROM users WHERE is_admin=0 AND is_active=1').fetchall()
   for x in us:c.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(x['id'],'📢 Yangi eʼlon',title))
   c.commit();flash('Eʼlon joylandi.','success')
 rows=c.execute('SELECT * FROM announcements ORDER BY id DESC').fetchall();c.close();body='''<div class="grid2"><div class="card"><h1>📢 E'lon</h1><form method="post"><input name="title" placeholder="Sarlavha" required><textarea name="content" placeholder="Matn" required></textarea><button class="btn purple">Yuborish</button></form></div><div class="card">{% for a in rows %}<div class="card"><h3>{{a['title']}}</h3><p>{{a['content']}}</p><a class="btn red" href="{{url_for('del_ann',aid=a['id'])}}">O'chirish</a></div>{% endfor %}</div></div>''';return layout('Eʼlonlar',body,rows=rows)

@app.route('/admin/announcement/delete/<int:aid>')
@admin_req
def del_ann(aid):
 c=con();c.execute('DELETE FROM announcements WHERE id=?',(aid,));c.commit();c.close();return redirect(url_for('admin_ann'))

@app.route('/admin/groups',methods=['GET','POST'])
@admin_req
def admin_groups():
 c=con()
 if request.method=='POST':
  c.execute('INSERT INTO groups_(name,description,keyword) VALUES(?,?,?)',(request.form.get('name',''),request.form.get('description',''),request.form.get('keyword','')));c.commit()
 rows=c.execute('SELECT * FROM groups_ ORDER BY id DESC').fetchall();c.close();body='''<div class="grid2"><div class="card"><h1>➕ Guruh</h1><form method="post"><input name="name" placeholder="Nomi" required><textarea name="description" placeholder="Tavsif"></textarea><input name="keyword" placeholder="Kalit so'z"><button class="btn green">Yaratish</button></form></div><div class="card">{% for g in rows %}<div class="card"><h3>{{g['name']}}</h3><p>{{g['description']}}</p><a class="btn red" href="{{url_for('del_group',gid=g['id'])}}">O'chirish</a></div>{% endfor %}</div></div>''';return layout('Admin guruhlar',body,rows=rows)

@app.route('/admin/group/delete/<int:gid>')
@admin_req
def del_group(gid):
 c=con();c.execute('DELETE FROM members WHERE group_id=?',(gid,));c.execute('DELETE FROM groups_ WHERE id=?',(gid,));c.commit();c.close();return redirect(url_for('admin_groups'))

@app.errorhandler(404)
def e404(e):return layout('404','<div class="card center"><h1>404 😕</h1><a class="btn" href="{{url_for("home")}}">Bosh sahifa</a></div>'),404

@app.errorhandler(413)
def e413(e):return layout('Fayl katta',"<div class='card center'><h1>📷 Rasm 4 MB dan kichik bo'lsin.</h1></div>"),413

# =========================================================
# PRO v4: MAKTAB ICHIDA AVTOMATIK QIZIQISH GURUHLARI
# =========================================================

def _norm(v):
    v = (v or "").lower().strip()
    v = v.replace("’", "'").replace("‘", "'").replace("`", "'")
    return re.sub(r"\s+", " ", v)


def _tags(v):
    v = (v or "").replace(";", ",").replace("|", ",")
    result, seen = [], set()
    for line in v.splitlines():
        for item in line.split(","):
            item = re.sub(r"\s+", " ", item).strip(" .,-_")
            if len(item) >= 2:
                key = _norm(item)
                if key not in seen:
                    seen.add(key)
                    result.append(item)
    if not result and (v or "").strip():
        result = [v.strip()]
    return result


def _school_groups(users):
    groups = {}
    for u in users:
        school = (u["school"] or "").strip()
        if not school:
            continue
        sk = (_norm(u["region"]), _norm(u["district"]), _norm(school))
        for tag in _tags(u["interests"]):
            tk = _norm(tag)
            key = sk + (tk,)
            groups.setdefault(key, {
                "region": u["region"],
                "district": u["district"],
                "school": school,
                "interest": tag,
                "members": []
            })["members"].append(u)
    rows = list(groups.values())
    rows.sort(key=lambda x: (-len(x["members"]), _norm(x["school"]), _norm(x["interest"])))
    return rows


@app.route("/dashboard")
@login_req
def dashboard():
    u = user()
    c = con()
    fav = c.execute("SELECT COUNT(*) n FROM favorites WHERE user_id=?", (u["id"],)).fetchone()["n"]
    my_groups = c.execute("SELECT COUNT(*) n FROM members WHERE user_id=?", (u["id"],)).fetchone()["n"]
    unread = c.execute("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND is_read=0", (u["id"],)).fetchone()["n"]
    school_users = []
    if u["school"]:
        school_users = c.execute(
            "SELECT * FROM users WHERE id!=? AND is_admin=0 AND is_active=1 "
            "AND lower(trim(region))=lower(trim(?)) AND lower(trim(district))=lower(trim(?)) "
            "AND lower(trim(school))=lower(trim(?)) ORDER BY id DESC LIMIT 12",
            (u["id"], u["region"], u["district"], u["school"])
        ).fetchall()
    c.close()
    vals = [u["first_name"],u["last_name"],u["region"],u["district"],u["school"],
            u["class_name"],u["interests"],u["bio"],u["photo"]]
    complete = round(sum(bool(x and str(x).strip()) for x in vals) / len(vals) * 100)

    body = '''
    <div class="hero"><h1>📊 Mening kabinetim</h1>
    <p class="muted">Profil va maktabdagi qiziqish guruhlarini boshqaring.</p></div><br>
    <div class="grid">
      <div class="card"><div class="stat">{{complete}}%</div>Profil to'liqligi</div>
      <div class="card"><div class="stat">{{fav}}</div>Saqlangan profil</div>
      <div class="card"><div class="stat">{{my_groups}}</div>Guruh a'zoligi</div>
      <div class="card"><div class="stat">{{unread}}</div>Yangi xabar</div>
      <div class="card"><div class="stat">{{school_users|length}}</div>Maktabdagi boshqa o'quvchi</div>
    </div><br>
    <div class="card"><h2>⚡ Tezkor bo'limlar</h2>
      <a class="btn green" href="{{url_for('edit')}}">✏️ Profil</a>
      <a class="btn purple" href="{{url_for('my_school')}}">🏫 Mening maktabim</a>
      <a class="btn" href="{{url_for('school_groups')}}">👥 Maktab guruhlari</a>
      <a class="btn" href="{{url_for('similar')}}">✨ Mos o'quvchilar</a>
    </div>
    {% if user['school'] %}<br><div class="card"><h2>🏫 {{user['school']}} dagi o'quvchilar</h2>
      <div class="grid">{% for x in school_users %}<div class="card">
      <h3>{{x['first_name']}} {{x['last_name']}}</h3><span class="badge">{{x['class_name'] or 'Sinf yoq'}}</span>
      <p>{{(x['interests'] or '—')[:120]}}</p>
      <a class="btn" href="{{url_for('profile',user_id=x['id'])}}">Profil</a>
      </div>{% else %}<p>Hozircha topilmadi.</p>{% endfor %}</div>
    </div>{% endif %}
    '''
    return layout("Kabinet", body, complete=complete, fav=fav, my_groups=my_groups,
                  unread=unread, school_users=school_users)


@app.route("/school-groups")
def school_groups():
    c = con()
    users = c.execute("SELECT * FROM users WHERE is_admin=0 AND is_active=1").fetchall()
    c.close()
    rows = _school_groups(users)

    region = request.args.get("region","").strip()
    district = request.args.get("district","").strip()
    school = request.args.get("school","").strip()
    tag = request.args.get("tag","").strip()

    if region:
        rows = [x for x in rows if _norm(x["region"]) == _norm(region)]
    if district:
        rows = [x for x in rows if _norm(x["district"]) == _norm(district)]
    if school:
        rows = [x for x in rows if _norm(x["school"]) == _norm(school)]
    if tag:
        rows = [x for x in rows if _norm(x["interest"]) == _norm(tag)]

    rows = [x for x in rows if len(x["members"]) >= 2]

    body = '''
    <div class="hero"><h1>🏫 Maktabdagi bir xil qiziqish guruhlari</h1>
    <p class="muted">Bir xil maktabdagi bir xil qiziqishlar avtomatik guruhlanadi.</p>
    <p class="small muted">Qiziqishlarni vergul bilan yozing: Python, futbol, kitob.</p></div><br>
    <div class="card"><form method="get"><div class="grid2">
      <div><label>Viloyat</label><select name="region"><option value="">Barchasi</option>
      {% for r in regions %}<option value="{{r}}" {% if r==region %}selected{% endif %}>{{r}}</option>{% endfor %}</select>
      <label>Tuman</label><input name="district" value="{{district}}"></div>
      <div><label>Maktab</label><input name="school" value="{{school}}" placeholder="12-maktab">
      <label>Qiziqish</label><input name="tag" value="{{tag}}" placeholder="Python"></div>
    </div><button class="btn">🔎 Qidirish</button>
    <a class="btn gray" href="{{url_for('school_groups')}}">Tozalash</a></form></div><br>
    <div class="card"><h2>👥 Guruhlar: {{rows|length}}</h2><div class="grid">
    {% for g in rows %}<div class="card"><h2>✨ {{g['interest']}}</h2>
      <p><b>🏫 {{g['school']}}</b></p><p class="muted">{{g['region']}} / {{g['district']}}</p>
      <span class="badge">👥 {{g['members']|length}} nafar</span><br><br>
      <a class="btn purple" href="{{url_for('school_group_detail',region=g['region'],district=g['district'],school=g['school'],tag=g['interest'])}}">Guruhni ochish</a>
    </div>{% else %}<p class="muted">Hozircha 2+ o'quvchili guruh topilmadi.</p>{% endfor %}</div></div>
    '''
    return layout("Maktab guruhlari", body, rows=rows, region=region,
                  district=district, school=school, tag=tag)


@app.route("/school-group")
def school_group_detail():
    region = request.args.get("region","").strip()
    district = request.args.get("district","").strip()
    school = request.args.get("school","").strip()
    tag = request.args.get("tag","").strip()

    c = con()
    users = c.execute(
        "SELECT * FROM users WHERE is_admin=0 AND is_active=1 "
        "AND lower(trim(region))=lower(trim(?)) AND lower(trim(district))=lower(trim(?)) "
        "AND lower(trim(school))=lower(trim(?)) ORDER BY first_name,last_name",
        (region,district,school)
    ).fetchall()
    c.close()

    members = [u for u in users if any(_norm(x)==_norm(tag) for x in _tags(u["interests"]))]

    body = '''
    <div class="hero"><h1>✨ {{tag}}</h1><p><b>🏫 {{school}}</b></p>
    <p class="muted">{{region}} / {{district}}</p><span class="badge">👥 {{members|length}} nafar</span></div><br>
    <div class="card"><h2>👥 Guruh a'zolari</h2>
    <p class="muted">Bu guruh avtomatik. O'quvchi shu qiziqishni profiliga yozsa, guruhda ko'rinadi.</p>
    <div class="grid">{% for u in members %}<div class="card">
      {% if u['photo'] %}<img class="avatar" src="{{url_for('static',filename='uploads/'+u['photo'])}}">{% else %}<div class="avatar center" style="padding-top:25px">👤</div>{% endif %}
      <h3>{{u['first_name']}} {{u['last_name']}}</h3><span class="badge">{{u['class_name'] or 'Sinf yoq'}}</span>
      <p>{{(u['interests'] or '')[:150]}}</p><a class="btn" href="{{url_for('profile',user_id=u['id'])}}">Profil</a>
    </div>{% else %}<p>Guruh bo'sh.</p>{% endfor %}</div></div>
    '''
    return layout("Maktab qiziqish guruhi", body, members=members,
                  region=region, district=district, school=school, tag=tag)


@app.route("/my-school")
@login_req
def my_school():
    u = user()
    if not u["school"]:
        flash("Avval profilingizga maktab nomini kiriting.","warning")
        return redirect(url_for("edit"))

    c = con()
    users = c.execute(
        "SELECT * FROM users WHERE is_admin=0 AND is_active=1 "
        "AND lower(trim(region))=lower(trim(?)) AND lower(trim(district))=lower(trim(?)) "
        "AND lower(trim(school))=lower(trim(?)) ORDER BY first_name,last_name",
        (u["region"],u["district"],u["school"])
    ).fetchall()
    c.close()

    rows = [x for x in _school_groups(users) if len(x["members"]) >= 2]
    my_keys = set(_norm(x) for x in _tags(u["interests"]))
    mine = [x for x in rows if _norm(x["interest"]) in my_keys]

    body = '''
    <div class="hero"><h1>🏫 Mening maktabim</h1>
    <p><b>{{user['school']}}</b></p><p class="muted">{{user['region']}} / {{user['district']}}</p>
    <span class="badge">👥 {{users|length}} faol o'quvchi</span></div><br>
    <div class="card"><h2>✨ Mening qiziqish guruhlarim</h2><div class="grid">
    {% for g in mine %}<div class="card"><h2>{{g['interest']}}</h2><span class="badge">{{g['members']|length}} nafar</span>
    <br><br><a class="btn purple" href="{{url_for('school_group_detail',region=g['region'],district=g['district'],school=g['school'],tag=g['interest'])}}">Guruhni ko'rish</a></div>
    {% else %}<p class="muted">Sizning qiziqishingiz bo'yicha guruh hali shakllanmagan.</p>{% endfor %}</div></div><br>
    <div class="card"><h2>📚 Maktabdagi barcha guruhlar</h2><div class="grid">
    {% for g in rows %}<div class="card"><h3>✨ {{g['interest']}}</h3><span class="badge">{{g['members']|length}} nafar</span>
    <br><br><a class="btn" href="{{url_for('school_group_detail',region=g['region'],district=g['district'],school=g['school'],tag=g['interest'])}}">Ochish</a></div>
    {% else %}<p>Hali guruh yo'q.</p>{% endfor %}</div></div>
    '''
    return layout("Mening maktabim", body, users=users, rows=rows, mine=mine)


@app.route("/interests")
def interests_directory():
    c = con()
    users = c.execute("SELECT * FROM users WHERE is_admin=0 AND is_active=1").fetchall()
    c.close()
    data = {}
    for u in users:
        for tag in _tags(u["interests"]):
            key = _norm(tag)
            if key:
                data.setdefault(key, {"name":tag,"count":0})["count"] += 1
    rows = sorted(data.values(), key=lambda x:(-x["count"],_norm(x["name"])))

    body = '''
    <div class="hero"><h1>🌍 Qiziqishlar katalogi</h1>
    <p class="muted">Bir xil qiziqishlarni tez topish.</p></div><br>
    <div class="grid">{% for x in rows %}<div class="card"><h2>✨ {{x['name']}}</h2>
    <span class="badge">{{x['count']}} ta profil</span><br><br>
    <a class="btn" href="{{url_for('students',q=x['name'])}}">O'quvchilar</a>
    <a class="btn purple" href="{{url_for('school_groups',tag=x['name'])}}">Maktab guruhlari</a></div>
    {% else %}<p>Qiziqishlar hali kiritilmagan.</p>{% endfor %}</div>
    '''
    return layout("Qiziqishlar katalogi", body, rows=rows)


@app.route("/api/school-groups")
def api_school_groups():
    c = con()
    users = c.execute("SELECT * FROM users WHERE is_admin=0 AND is_active=1").fetchall()
    c.close()
    rows = [x for x in _school_groups(users) if len(x["members"]) >= 2]
    return {
        "count": len(rows),
        "groups": [{
            "region":x["region"], "district":x["district"], "school":x["school"],
            "interest":x["interest"], "members":len(x["members"]),
            "member_ids":[u["id"] for u in x["members"]]
        } for x in rows]
    }


@app.route("/admin/school-groups")
@admin_req
def admin_school_groups():
    c = con()
    users = c.execute("SELECT * FROM users WHERE is_admin=0 AND is_active=1").fetchall()
    c.close()
    rows = [x for x in _school_groups(users) if len(x["members"]) >= 2]

    body = '''
    <div class="hero"><h1>🏫 Maktab guruhlari nazorati</h1>
    <p class="muted">Avtomatik yaratilgan bir xil qiziqish guruhlari.</p></div><br>
    <div class="card wrap"><table><tr><th>Maktab</th><th>Qiziqish</th><th>A'zolar</th><th></th></tr>
    {% for g in rows %}<tr><td>{{g['school']}}<br><span class="muted">{{g['region']}} / {{g['district']}}</span></td>
    <td>✨ {{g['interest']}}</td><td>{{g['members']|length}}</td>
    <td><a class="btn" href="{{url_for('school_group_detail',region=g['region'],district=g['district'],school=g['school'],tag=g['interest'])}}">Ochish</a></td></tr>
    {% else %}<tr><td colspan="4">Guruhlar yo'q.</td></tr>{% endfor %}</table></div>
    '''
    return layout("Admin maktab guruhlari", body, rows=rows)

# =========================================================
# AI USTOZ: MA'LUMOT + O'RGATISH + SAVOL-JAVOB
# =========================================================

def save_ai_message(user_id, role, message, interest=""):
    c = con()
    c.execute(
        "INSERT INTO ai_messages(user_id,role,message,interest) VALUES(?,?,?,?)",
        (user_id, role, message[:12000], interest[:300])
    )
    c.commit()
    c.close()


@app.route("/ai", methods=["GET", "POST"])
@login_req
def ai_mentor():
    u = user()
    selected = request.args.get("interest", "").strip()

    if request.method == "POST":
        question = request.form.get("question", "").strip()
        mode = request.form.get("mode", "answer").strip()
        interest = request.form.get("interest", "").strip() or selected

        if not interest:
            my_tags = _tags(u["interests"])
            interest = my_tags[0] if my_tags else "umumiy ta'lim"

        if not question:
            flash("Savolingizni yozing.", "warning")
            return redirect(url_for("ai_mentor", interest=interest))

        save_ai_message(u["id"], "user", question, interest)
        answer, err = ai_request(question, interest, mode)

        if err:
            save_ai_message(u["id"], "error", err, interest)
            flash(err, "danger")
        else:
            save_ai_message(u["id"], "assistant", answer, interest)

        return redirect(url_for("ai_mentor", interest=interest))

    c = con()
    history = c.execute(
        "SELECT * FROM ai_messages WHERE user_id=? ORDER BY id DESC LIMIT 20",
        (u["id"],)
    ).fetchall()
    c.close()

    interests = _tags(u["interests"])
    if selected and selected not in interests:
        interests.insert(0, selected)
    if not selected and interests:
        selected = interests[0]

    body = '''
    <div class="hero">
      <h1>🤖 AI Ustoz</h1>
      <p class="muted">Qiziqishingizni tanlang — AI sizga shu mavzuni tushuntiradi, o'rgatadi va savollaringizga javob beradi.</p>
    </div>
    <br>

    <div class="card">
      <h2>🎯 Mavzu</h2>
      {% if interests %}
        <div class="grid">
        {% for x in interests %}
          <a class="card" href="{{url_for('ai_mentor',interest=x)}}" style="text-decoration:none">
            <h3>✨ {{x}}</h3>
            <span class="badge">{% if x==selected %}Tanlangan{% else %}O'rganish{% endif %}</span>
          </a>
        {% endfor %}
        </div>
      {% else %}
        <p class="muted">Profilingizga "Mening qiziqishlarim"ni yozsangiz, AI shu mavzular bo'yicha sizga mos darslar beradi.</p>
        <a class="btn green" href="{{url_for('edit')}}">✏️ Qiziqishlarimni yozish</a>
      {% endif %}
    </div>

    <br>
    <div class="grid">
      <div class="card">
        <h2>📚 O'rganishni boshlash</h2>
        <p class="muted">AI mavzuni noldan boshlab o'rgatadi.</p>
        <form method="post">
          <input type="hidden" name="interest" value="{{selected}}">
          <input type="hidden" name="mode" value="learn">
          <input type="hidden" name="question" value="Menga shu mavzuni noldan boshlab o'rgat. Avval asosiy tushunchalarni tushuntir, keyin amaliy mashq ber.">
          <button class="btn purple">🎓 Darsni boshlash</button>
        </form>
      </div>
      <div class="card">
        <h2>📝 7 kunlik reja</h2>
        <p class="muted">Har kuni nima o'rganishni AI tuzib beradi.</p>
        <form method="post">
          <input type="hidden" name="interest" value="{{selected}}">
          <input type="hidden" name="mode" value="plan">
          <input type="hidden" name="question" value="Shu qiziqishim bo'yicha 7 kunlik o'quv reja tuzib ber.">
          <button class="btn green">📅 Reja tuzish</button>
        </form>
      </div>
      <div class="card">
        <h2>❓ Test</h2>
        <p class="muted">O'rgangan mavzuni savollar bilan tekshirish.</p>
        <form method="post">
          <input type="hidden" name="interest" value="{{selected}}">
          <input type="hidden" name="mode" value="quiz">
          <input type="hidden" name="question" value="Shu mavzu bo'yicha bilimimni tekshirish uchun 5 ta savol ber.">
          <button class="btn">🧠 Test boshlash</button>
        </form>
      </div>
    </div>

    <br>
    <div class="card">
      <h2>💬 Savolingizni bering</h2>
      <p class="muted">Masalan: "Python'da for sikli qanday ishlaydi?"</p>
      <form method="post">
        <label>Tanlangan qiziqish</label>
        <input name="interest" value="{{selected}}" placeholder="Masalan: Python">
        <label>Savol</label>
        <textarea name="question" placeholder="Qiziqayotgan narsangiz haqida savol yozing..." required></textarea>
        <input type="hidden" name="mode" value="answer">
        <button class="btn purple">🤖 AI dan javob olish</button>
      </form>
    </div>

    <br>
    <div class="card">
      <h2>🕘 So'nggi suhbatlar</h2>
      {% for m in history %}
        <div class="card">
          <span class="badge">{% if m['role']=='user' %}Siz{% elif m['role']=='assistant' %}AI Ustoz{% else %}Xatolik{% endif %}</span>
          {% if m['interest'] %}<span class="badge">✨ {{m['interest']}}</span>{% endif %}
          <p style="white-space:pre-wrap">{{m['message']}}</p>
          <small class="muted">{{m['created_at']}}</small>
        </div>
      {% else %}
        <p class="muted">Hali suhbat yo'q.</p>
      {% endfor %}
    </div>

    <br>
    <div class="card">
      <h3>🔐 AI kaliti haqida</h3>
      <p class="muted">AI ishlashi uchun server/Pydroid papkasida <b>ai_key.txt</b> fayli bo'lishi va ichida API kalit bo'lishi kerak. Kalit brauzerga yuborilmaydi.</p>
    </div>
    '''
    return layout("AI Ustoz", body, interests=interests, selected=selected, history=history)


@app.route("/ai/learn")
@login_req
def ai_learn():
    u = user()
    interest = request.args.get("interest", "").strip()
    if not interest:
        tags = _tags(u["interests"])
        interest = tags[0] if tags else "umumiy ta'lim"
    return redirect(url_for("ai_mentor", interest=interest))


@app.route("/ai/clear")
@login_req
def ai_clear():
    c = con()
    c.execute("DELETE FROM ai_messages WHERE user_id=?", (user()["id"],))
    c.commit()
    c.close()
    flash("AI suhbat tarixi tozalandi.", "success")
    return redirect(url_for("ai_mentor"))


@app.route("/api/ai", methods=["POST"])
@login_req
def api_ai():
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()
    interest = str(data.get("interest", "")).strip()
    mode = str(data.get("mode", "answer")).strip()

    if not question:
        return {"ok": False, "error": "question kerak"}, 400

    if not interest:
        tags = _tags(user()["interests"])
        interest = tags[0] if tags else "umumiy ta'lim"

    answer, err = ai_request(question, interest, mode)
    if err:
        return {"ok": False, "error": err}, 500

    save_ai_message(user()["id"], "user", question, interest)
    save_ai_message(user()["id"], "assistant", answer, interest)
    return {"ok": True, "interest": interest, "answer": answer, "model": AI_MODEL}

if __name__=='__main__':
 print('QIZIQISHLARIM PRO v3')
 print('http://127.0.0.1:5000')
 print('ADMIN: admin / 12345')
 app.run(host='127.0.0.1',port=5000,debug=False)
