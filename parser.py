import io, re
import pdfplumber
from models import Aspect, Chart, Point
from astrology import SIGN_CODES, absolute, house_of, opposite_node, orb_weight, south_node_aspects

POINT_NAMES = {
    "A":"Ήλιος", "B":"Σελήνη", "C":"Ερμής", "D":"Αφροδίτη", "E":"Άρης", "F":"Δίας",
    "G":"Κρόνος", "O":"Ουρανός", "I":"Ποσειδώνας", "J":"Πλούτωνας", "L":"Βόρειος Δεσμός", "N":"Χείρωνας",
    "Q":"Ωροσκόπος", "T":"Μεσουράνημα"
}
ASPECT_GLYPHS = {"m":"Σύνοδος", "q":"Εξάγωνο", "o":"Τετράγωνο", "p":"Τρίγωνο", "s":"Χιαστί όψη 150°", "n":"Αντίθεση"}
LONG_RE = re.compile(r"(\d{1,2})°\s*(\d{1,2})'\s*(\d{1,2})\"")

def _point(code, name, sign_code, d, m, s, house=None, retro=False, kind="planet"):
    sign = SIGN_CODES[sign_code]
    return Point(code, name, sign, int(d), int(m), int(s), absolute(sign,int(d),int(m),int(s)), int(house) if house else None, retro, kind)

def _metadata(text: str, filename: str):
    first = text.splitlines()[:14]
    name = filename.rsplit(".",1)[0]
    date = time = place = ""
    for line in first:
        if "Time" in line and not time:
            left, right = line.split("Time",1); name = re.sub(r"^[D\s]+", "", left).strip() or name
            mt = re.search(r"(\d{1,2}:\d{2}\s*[ap]\.m\.)", right); time = mt.group(1) if mt else ""
        if "born on" in line:
            date = line.split("born on",1)[1].split("Univ.Time",1)[0].strip()
        if line.strip().startswith("in "):
            place = line.strip()[3:].split("Sid. Time",1)[0].strip()
    method = "Placidus" if "Houses (Plac.)" in text else "Δεν αναγνωρίστηκε"
    return name, date, time, place, method

def _parse_positions(page):
    words=page.extract_words(x_tolerance=1,y_tolerance=2,keep_blank_chars=False)
    rows={}
    for w in words: rows.setdefault(round(w['top'],1),[]).append(w)
    points=[]; cusps=[]
    wanted=["A","B","C","D","E","F","G","O","I","J","K","L","N"]
    cusp_order=[]
    for y,ws in sorted(rows.items()):
        code=next((w['text'] for w in ws if w['text'] in wanted and 30<=w['x0']<45),None)
        if not code: continue
        sign_word=next((w for w in ws if w['text'] in SIGN_CODES and 100<w['x0']<120),None)
        cusp_sign=next((w for w in ws if w['text'] in SIGN_CODES and 440<w['x0']<460),None)
        data=[]
        for y2,ws2 in rows.items():
            if 3<y2-y<7: data=ws2; break
        if not sign_word or not data: continue
        longitude=''.join(w['text'] for w in sorted(data,key=lambda z:z['x0']) if 120<w['x0']<178)
        lm=LONG_RE.search(longitude)
        house_word=next((w for w in data if 184<w['x0']<207 and w['text'].isdigit()),None)
        if lm and house_word and code in POINT_NAMES:
            # In Astrodienst's embedded font the retrograde glyph is commonly
            # extracted as '#'.  A negative daily-motion value on the data row
            # is an independent confirmation.  '(' is a station marker and
            # must not by itself turn a planet into retrograde.
            negative_motion = any(w['text'] == '-' and 210 < w['x0'] < 250 for w in data)
            # The True Node is not a planet, but its signed daily motion still
            # needs to be preserved.  It is described later as "retrograde
            # movement", rather than as a retrograde planet.
            retrograde = any(w['text'] == '#' for w in ws) or negative_motion
            points.append(_point(code,POINT_NAMES[code],sign_word['text'],*lm.groups(),house_word['text'],retrograde,"node" if code=='L' else "planet"))
        if cusp_sign:
            cusp_long=''.join(w['text'] for w in sorted(data,key=lambda z:z['x0']) if 460<w['x0']<510)
            cm=LONG_RE.search(cusp_long)
            label=next((w['text'] for w in data if 410<w['x0']<450),str(len(cusp_order)+1))
            if cm: cusp_order.append((label,cusp_sign['text'],*cm.groups()))
    for i,(_,sg,d,mi,se) in enumerate(cusp_order[:12],1):
        cusps.append(_point(f"H{i}",f"{i}ος Οίκος",sg,d,mi,se,kind="cusp"))
    return points,cusps

def _parse_aspect_grid(page, points_by_code):
    words = page.extract_words(x_tolerance=1, y_tolerance=2, keep_blank_chars=False)
    aspect_word = next((w for w in words if w["text"] == "Aspects"), None)
    if not aspect_word: return []
    rows = {}
    for w in words:
        if w["top"] <= aspect_word["top"] + 12: continue
        rows.setdefault(round(w["top"],1), []).append(w)
    row_codes = [c for c in ["B","C","D","E","F","G","O","I","J","L","N","Q","T"] if c in points_by_code]
    col_codes = [c for c in ["A","B","C","D","E","F","G","O","I","J","L","N","Q"] if c in points_by_code]
    col_x = [56 + 41.4*i for i in range(len(col_codes))]
    result=[]
    for y, ws in sorted(rows.items()):
        row_code = next((w["text"] for w in ws if w["text"] in row_codes and w["x0"] < 45), None)
        if not row_code: continue
        glyphs = [w for w in ws if w["text"] in ASPECT_GLYPHS]
        orb_words = []
        for y2, ws2 in rows.items():
            if 3 < y2-y < 7:
                orb_words.extend([w for w in ws2 if re.match(r"^-?\d+°\d{2}[as]$", w["text"])])
        for g in glyphs:
            idx = min(range(len(col_x)), key=lambda i: abs((g["x0"]+g["x1"])/2-col_x[i]))
            if idx >= len(col_codes) or col_codes[idx] == row_code: continue
            ow = min(orb_words, key=lambda w: abs((w["x0"]+w["x1"])/2-(col_x[idx]+21)), default=None)
            if not ow: continue
            mo = re.match(r"(-?)(\d+)°(\d{2})([as])", ow["text"])
            orb = int(mo.group(2)) + int(mo.group(3))/60
            result.append(Aspect(points_by_code[col_codes[idx]].name, points_by_code[row_code].name, ASPECT_GLYPHS[g["text"]], orb, f"{int(mo.group(2))}°{int(mo.group(3)):02d}′", orb_weight(orb), "Πίνακας Astrodienst", mo.group(4)=="a"))
    return result

def parse_astrodienst_pdf(data: bytes, filename: str) -> Chart:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        page=pdf.pages[0]; text=page.extract_text(layout=True) or ""
        name,date,time,place,method=_metadata(text, filename)
        points,cusps=_parse_positions(page)
        if len(cusps) < 12:
            raise ValueError(f"Αναγνωρίστηκαν μόνο {len(cusps)} από τις 12 ακμές. Χρειάζεται Astrodienst Natal Chart (Data Sheet).")
        if len(points)<10: raise ValueError(f"Αναγνωρίστηκαν μόνο {len(points)} πλανήτες/σημεία.")
        for p in points: p.house=house_of(p.absolute,cusps)
        asc=Point("Q","Ωροσκόπος",cusps[0].sign,cusps[0].degree,cusps[0].minute,cusps[0].second,cusps[0].absolute,kind="angle")
        mc=Point("T","Μεσουράνημα",cusps[9].sign,cusps[9].degree,cusps[9].minute,cusps[9].second,cusps[9].absolute,kind="angle")
        points.extend([asc,mc])
        node=next((p for p in points if p.name=="Βόρειος Δεσμός"),None)
        if node:
            south=opposite_node(node); south.house=house_of(south.absolute,cusps); points.append(south)
        by_code={p.code:p for p in points}
        aspects=_parse_aspect_grid(page,by_code)
        if node:
            aspects.extend(south_node_aspects(aspects))
        hard=[a for a in aspects if a.aspect in ("Τετράγωνο","Αντίθεση")]
        warnings=[]
        if not hard: warnings.append("Δεν αναγνωρίστηκε ο πίνακας δυναμικών όψεων· μην προχωρήσεις χωρίς χειροκίνητο έλεγχο.")
        return Chart(name,date,time,place,method,points,cusps,aspects,warnings)
