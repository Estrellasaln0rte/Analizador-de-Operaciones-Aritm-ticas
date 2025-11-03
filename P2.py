import os
import datetime
import tkinter
from tkinter import filedialog, messagebox, scrolledtext
import webbrowser

#rutas
#convert en ruta abs.carpeta.archivo actual
ABS_PATH = os.path.abspath(os.path.dirname(__file__))
#dirigir ruta abs a carpetas 
DOCS_DIR = os.path.join(ABS_PATH, "docs")
OUTPUTS_DIR = os.path.join(ABS_PATH, "outputs")

#ver carpetas exist
def ensure_dirs():
    os.makedirs(DOCS_DIR, exist_ok=True)
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    """
    escapar HTML: genera una vista previa segura en HTML de un texto, recortándolo a n caracteres y escapando símbolos especiales
    """
def escape_html_preview(s, n=500):
    s = s[:n] + ("..." if len(s) > n else "")
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\n", "<br/>"))

#plantilla html
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>{titulo}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            background-color: #f4f4f4;
            margin: 20px;
        }}
        h1 {{
            text-align: center;
            color: #E3AAAA;
        }}
        table {{
            border-collapse: collapse;
            width: 90%;
            margin: auto;
            background: white;
            box-shadow: 0px 2px 8px rgba(0,0,0,0.1);
            border-radius: 8px;
            overflow: hidden;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 10px;
            text-align: center;
        }}
        th {{
            background-color: #9E366D;
            color: white;
        }}
        .footer {{
            text-align:center;
            margin-top: 18px;
            color: #666;
        }}
    </style>
</head>
<body>
    <h1>{titulo}</h1>
    <table>
        <thead>
            <tr>{encabezados}</tr>
        </thead>
        <tbody>
            {filas}
        </tbody>
    </table>
    <div class="footer">
        Generado automáticamente el {fecha}
    </div>
</body>
</html>
"""

def html_tabla(titulo, headers, rows):
    th = "".join(f"<th>{h}</th>" for h in headers)
    cuerpo = "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return HTML_TEMPLATE.format(
        titulo=titulo,
        encabezados=th,
        filas=cuerpo,
        fecha=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    )

#basicos del analizador
def leer_txt(ruta):
    with open(ruta, "r", encoding="utf-8", errors="strict") as f:
        return f.read()

def crear_token(tipo, lexema, fila, columna, valor=None):
    return {"tipo": tipo, "lexema": lexema, "fila": fila, "columna": columna, "valor": valor}

def crear_error(lexema, tipo, fila, columna):
    return {"lexema": lexema, "tipo": tipo, "fila": fila, "columna": columna}

def es_espacio(c): 
    return c in " \t\r\n"

def crear_estado(texto):
    return {"texto": texto, "i": 0, "n": len(texto), "fila": 1, "col": 1, "tokens": [], "errores": []}

def mirar(estado):
    i = estado["i"]
    return estado["texto"][i] if i < estado["n"] else None

def avanzar(estado):
    c = mirar(estado)
    if c is None: 
        return None
    estado["i"] += 1
    if c == "\n":
        estado["fila"] += 1
        estado["col"] = 1
    else:
        estado["col"] += 1
    return c

def agregar_error(estado, lexema, tipo, fila=None, col=None):
    if fila is None: fila = estado["fila"]
    if col is None: col = estado["col"]
    estado["errores"].append(crear_error(lexema, tipo, fila, col))

#lectura de etiquetas
def lex_etiqueta(estado):
    assert mirar(estado) == "<"
    start_f, start_c = estado["fila"], estado["col"]
    buf = [avanzar(estado)]#consume <
    while True:
        c = mirar(estado)
        if c is None:
            agregar_error(estado, "".join(buf), "Etiqueta no cerrada", start_f, start_c)
            return None, start_f, start_c
        buf.append(avanzar(estado))
        if c == ">":
            break
    return "".join(buf), start_f, start_c

def extraer_hasta_cierre(estado, nombre_cierre):
    start_f, start_c = estado["fila"], estado["col"]
    buf = []
    while True:
        c = mirar(estado)
        if c is None:
            agregar_error(estado, f"</{nombre_cierre}> faltante", "Cierre encontrado", start_f, start_c)
            return None, None, None
        if c == "<":
            content, rf, rc = lex_etiqueta(estado)
            if content is None: 
                return None, None, None
            interno = content[1:-1].strip()
            if interno.upper().startswith("/"):
                #ver cierre correcto
                #quita <>
                if interno[1:].strip().upper() == nombre_cierre.upper():
                    return "".join(buf), rf, rc
                else:
                    #cierre de otra cosa
                    buf.append(content)
            else:
                #otra apertura dentro
                buf.append(content)
        else:
            buf.append(avanzar(estado))

#aplicación dfa
class DFA:
    #constructor
    def __init__(self, alfabeto, transiciones, estado_inicial, finales, estado_error):
        self.alfabeto=set(alfabeto)
        self.transiciones=transiciones
        self.estado_inicial=estado_inicial
        self.finales=set(finales)
        self.estado_error=estado_error

    def mover(self, e, s):
        return self.transiciones.get(e, {}).get(s, self.estado_error)

    def acepta(self, simbolos, recolector_traza=None):
        """
        posición, símbolo, estado origen y destino
        """
        e=self.estado_inicial
        for idx,s in enumerate(simbolos):
            nxt = self.mover(e,s) if s in self.alfabeto else self.estado_error
            if recolector_traza is not None:
                recolector_traza.append({"pos":idx,"simbolo":s,"desde":e,"hasta":nxt})
            e=nxt
        return e in self.finales

class NumeroRecognizer:
    """
    Reconoce er
        (+|-) ? s* digit+ s* ( . s* digit+ ) ?
    Donde:
    's' es cualquier espacio ' ', '\\t', '\\r', '\\n'
    """
    def __init__(self, allow_slash=True, allow_espacios=True):
        self.allow_slash=allow_slash
        self.allow_espacios=allow_espacios
        self.alfabeto={"digit","+","-",".","s"}
        if allow_slash:
            self.alfabeto.add("/")
        self.dfa = DFA(
            self.alfabeto,
            {
                "q0":{"s":"q0" if allow_espacios else "E","+":"qS","-":"qS","digit":"qD",".":"E","/":"E"},
                "qS":{"s":"qS" if allow_espacios else "E","digit":"qD",".":"E","+":"E","-":"E","/":"E"},
                "qD":{"digit":"qD",".":"qSep","/":"qSep" if allow_slash else "E","s":"qA" if allow_espacios else "E"},
                "qSep":{"s":"qSep" if allow_espacios else "E","digit":"qF",".":"E","/":"E","+":"E","-":"E"},
                "qF":{"digit":"qF","s":"qA" if allow_espacios else "E",".":"E","/":"E","+":"E","-":"E"},
                "qA":{"s":"qA" if allow_espacios else "E","digit":"E",".":"E","/":"E","+":"E","-":"E"},
                "E":{}
            },
            "q0", {"qD","qF","qA"}, "E"
        )

    def _sym(self,ch):
        if ch in " \t\r\n": return "s"
        if '0'<=ch<='9': return "digit"
        if ch in "+-.": return ch
        return None

    def es_valido(self,s,recolector_traza=None):
        if s is None: return False
        s=s.strip()
        if s=="": return False
        return self.dfa.acepta([self._sym(ch) or "__INV__" for ch in s], recolector_traza)

#reconocer numeros con espacios pero no /
_num = NumeroRecognizer(allow_slash=False, allow_espacios=True)

def validar_numero_formato(s, recolector_traza=None):
    return _num.es_valido(s, recolector_traza)

def validar_entero_formato(s):
    if s is None: return False
    s=s.strip()
    if s=="": return False
    i=1 if s[0] in "+-" else 0
    if i>=len(s): return False
    return all('0'<=ch<='9' for ch in s[i:])

#analisis lexico a tokens
VALID_TOKENS = {"SUMA","RESTA","MULTIPLICACION","DIVISION","POTENCIA","RAIZ","INVERSO","MOD"}

def procesar_operacion_apertura(estado, interno, fila, col):
    rest = interno[len("OPERACION"):].strip()
    if not rest.startswith("="):
        agregar_error(estado, f"<Operacion{rest}>","Format ode operacion invalido", fila, col); 
        return
    nombre = rest[1:].strip().split()[0] if rest[1:].strip() else ""
    up = nombre.upper()
    if up in VALID_TOKENS:
        estado["tokens"].append(crear_token("OPEN_OPERACION", f"<Operacion= {up}>", fila, col, valor=up))
    else:
        agregar_error(estado, f"<Operacion={nombre}>","Nombre de operacion invalido", fila, col)

def analizar(estado, recolectar_trazas=False):
    while True:
        c=mirar(estado)
        if c is None: break
        if es_espacio(c): 
            avanzar(estado); 
            continue
        if c=="<":
            content, rf, rc = lex_etiqueta(estado)
            if content is None: 
                continue
            interno=content[1:-1].strip()
            up=interno.upper()

            # cierres
            if up.startswith("/"):
                name = up[1:].strip()
                tipo = {"OPERACION":"CLOSE_OPERACION","NUMERO":"CLOSE_NUMERO","P":"CLOSE_P","R":"CLOSE_R"}.get(name)
                if tipo: 
                    estado["tokens"].append(crear_token(tipo, content, rf, rc))
                else: 
                    agregar_error(estado, content, "Cierre de etiqueta desconocido", rf, rc)
                continue

            # aperturas
            if up.startswith("OPERACION"):
                procesar_operacion_apertura(estado, interno, rf, rc)
                continue

            if up=="NUMERO":
                contenido, _, _ = extraer_hasta_cierre(estado, "NUMERO")
                if contenido is None: 
                    continue
                val = contenido.strip()
                if not val:
                    agregar_error(estado, "<Numero> vacío","Numero vacio", rf, rc)
                else:
                    traza=[] if recolectar_trazas else None
                    if validar_numero_formato(val,traza):
                        estado["tokens"].append(crear_token("NUMERO", val, rf, rc, valor=val))
                    else:
                        # En errores dejamos opcionalmente la traza para depurar el DFA.
                        agregar_error(estado, f"{val} TRAZA={traza}" if traza else val, "Numero invalido", rf, rc)
                continue

            if up=="P":
                cont,_,_=extraer_hasta_cierre(estado,"P")
                if cont is None: 
                    continue
                v=cont.strip()
                if validar_entero_formato(v):
                    estado["tokens"].append(crear_token("P_VAL", v, rf, rc, valor=v))
                else:
                    agregar_error(estado, v, "Potencia invalido", rf, rc)
                continue

            if up=="R":
                cont,_,_=extraer_hasta_cierre(estado,"R")
                if cont is None: 
                    continue
                v=cont.strip()
                if validar_entero_formato(v) and not v.startswith("-"):
                    estado["tokens"].append(crear_token("R_VAL", v, rf, rc, valor=v))
                elif validar_entero_formato(v) and v.startswith("-"):
                    agregar_error(estado, v, "Raiz debe ser positivo", rf, rc)
                else:
                    agregar_error(estado, v, "Raiz invalido", rf, rc)
                continue

            # etiqueta no reconocida
            agregar_error(estado, content, "Etiqueta desconocida", rf, rc)
            continue

        # texto suelto fuera de etiqueta
        agregar_error(estado, avanzar(estado), "Texto fuera de etiqueta", estado["fila"], estado["col"])

    return estado["tokens"], estado["errores"]

#pareseo resolucion operaciones
class NUMERONode:
    def __init__(self, value_str): 
        self.value=float(value_str)
    def __repr__(self): 
        return f"NUMERO({self.value})"

class OpNode:
    def __init__(self, kind, children=None, p=None, r=None):
        self.kind=kind
        self.children=list(children or [])
        self.p=p
        self.r=r
    def __repr__(self):
        tail=[]
        if self.p is not None: tail.append(f"P={self.p}")
        if self.r is not None: tail.append(f"R={self.r}")
        return f"Op({self.kind}, {self.children}{', '+', '.join(tail) if tail else ''})"

def _parse_operation(tokens, i):
    assert tokens[i]["tipo"] == "OPEN_OPERACION"
    op = tokens[i]["valor"]
    fila0 = tokens[i]["fila"]
    col0  = tokens[i]["columna"]

    children = []
    p = None
    r = None
    j = i + 1
    L = len(tokens)
    invalid_block = False

    if tokens[i].get("invalid") is True:
        invalid_block = True

    exact = {"INVERSO": 1, "MOD": 2, "POTENCIA": 1, "RAIZ": 1}
    needs_P = (op == "POTENCIA")
    needs_R = (op == "RAIZ")

    def done_exact():
        if op not in exact:
            return False
        if len(children) != exact[op]:
            return False
        if needs_P and (p is None):
            return False
        if needs_R and (r is None):
            return False
        return True

    while j < L and tokens[j]["tipo"] != "CLOSE_OPERACION":
        t = tokens[j]
        tt = t["tipo"]

        if tt == "NUMERO":
            children.append(NUMERONode(t["valor"]))

        elif tt == "OPEN_OPERACION":
            sub, j2 = _parse_operation(tokens, j)
            if getattr(sub, "invalida", False):
                invalid_block = True
            children.append(sub)
            j = j2

        elif tt == "P_VAL":
            try:
                p = int(t["valor"])
            except Exception:
                p = None
                invalid_block = True 

        elif tt == "R_VAL":
            try:
                r = int(t["valor"])
            except Exception:
                r = None
                invalid_block = True

        elif tt in ("CLOSE_NUMERO", "CLOSE_P", "CLOSE_R"):
            invalid_block = True

        else:
            invalid_block = True

        j += 1


        if done_exact():
            if j < L and tokens[j]["tipo"] != "CLOSE_OPERACION":
                invalid_block = True
                _add_parser_error(fila0, col0, "Cierre operacion faltante",
                                  f"cierre </Operacion> faltante para {op}")
                node = OpNode(op, children, p=p, r=r)
                node.invalid = True
                return node, j - 1

    #no mas tokens y no hubo CLOSE
    if j >= L:
        invalid_block = True
        _add_parser_error(fila0, col0, "Cierre de operacion faltante",
                          f"Falta </Operacion> para {op}")
        node = OpNode(op, children, p=p, r=r)
        node.invalid = True
        return node, j

    #CLOSE_OPERACION encontrado
    node = OpNode(op, children, p=p, r=r)
    if invalid_block:
        node.invalid = True
    return node, j

def parse_all_operations(tokens):
    out = []
    i = 0
    L = len(tokens)
    while i < L:
        t = tokens[i]
        if t["tipo"] == "OPEN_OPERACION":
            node, j = _parse_operation(tokens, i)
            out.append(node)
            i = j + 1
        else:
            i += 1
    return out

_PARSER_ERRORS = []

def _add_parser_error(fila, col, tipo, detalle):
    _PARSER_ERRORS.append((detalle, tipo, fila, col))

#VALIDACIÓN SEMÁNTICA 
def op_is_valid(node):
    for ch in getattr(node, "children", []):
        if isinstance(ch, OpNode) and (not op_is_valid(ch)):
            return False

    k=node.kind
    n=len(node.children)
    if k in {"SUMA","RESTA","MULTIPLICACION","DIVISION"}:
        return n >= 2
    if k == "MOD":
        return n == 2
    if k == "INVERSO":
        return n == 1
    if k == "POTENCIA":
        return n == 1 and (node.p is not None)
    if k == "RAIZ":
        return n == 1 and (node.r is not None)
    return False

def filter_valid_asts(asts):
    def is_valid(node):
        # Bandera de invalidez estructural
        if getattr(node, "invalid", False):
            return False

        # Validar hijos (recursivo)
        for ch in getattr(node, "children", []):
            if isinstance(ch, OpNode):
                if not is_valid(ch):
                    return False
            # NUMERONode siempre válido

        # Validación semántica por aridad / etiquetas
        k = node.kind
        n = len(node.children)
        if k in {"SUMA","RESTA","MULTIPLICACION","DIVISION"}:
            return n >= 2
        if k == "INVERSO":
            return n == 1
        if k == "MOD":
            return n == 2
        if k == "POTENCIA":
            return n == 1 and (node.p is not None)
        if k == "RAIZ":
            return n == 1 and (node.r is not None)
        return False

    return [n for n in asts if is_valid(n)]

#evaluar
def _eval_ltr(values, op):
    if not values: 
        return 0.0
    acc=values[0]
    for x in values[1:]:
        if op=="SUMA": acc+=x
        elif op=="RESTA": acc-=x
        elif op=="MULTIPLICACION": acc*=x
        elif op=="DIVISION": acc/=x
        elif op=="MOD": acc%=x
    return acc

def _eval(node):
    if isinstance(node, NUMERONode): 
        return node.value
    vals=[_eval(ch) for ch in node.children]
    k=node.kind
    if k=="INVERSO":
        return 1.0/vals[0]
    if k=="POTENCIA":
        return vals[0]**node.p
    if k=="RAIZ":
        return vals[0]**(1.0/node.r)
    if k in {"SUMA","RESTA","MULTIPLICACION","DIVISION","MOD"}:
        return _eval_ltr(vals,k)
    raise ValueError("Operación no soportada: "+k)

def pretty(node):
    if isinstance(node, NUMERONode): 
        return f"{node.value:.15g}"
    ch=[pretty(c) for c in node.children]
    k=node.kind
    if k=="SUMA": return "("+" + ".join(ch)+")"
    if k=="RESTA": return "("+" - ".join(ch)+")"
    if k=="MULTIPLICACION": return "("+" * ".join(ch)+")"
    if k=="DIVISION": return "("+" / ".join(ch)+")"
    if k=="MOD": return "("+" % ".join(ch)+")"
    if k=="INVERSO": return "(1 / "+ch[0]+")"
    if k=="POTENCIA": return f"({ch[0]} ^ {node.p})"
    if k=="RAIZ":     return f"(root_{node.r} {ch[0]})"
    return f"({k} {', '.join(ch)})"

def evaluate_asts(asts):
    #solo validos
    return [{"index":i,"expr":pretty(n),"value":_eval(n),"root":n} for i,n in enumerate(asts,1)]

#generacion de arboles
def _collect_tree(root):
    """
    Convierte un AST en listas de nodos/aristas para graficación.
    """
    nodes=[]
    edges=[]
    counter={"n":0}
    def new_id():
        counter["n"]+=1
        return counter["n"]
    def add(label):
        nid=new_id()
        nodes.append({"id":nid,"label":label})
        return nid
    def walk(node,parent=None):
        if isinstance(node, NUMERONode):
            nid=add(f"{node.value:.15g}")
        else:
            title = f"POTENCIA (P={node.p})" if node.kind=="POTENCIA" else \
                    f"RAIZ (R={node.r})" if node.kind=="RAIZ" else node.kind.title()
            nid=add(title)
        if parent is not None:
            edges.append((parent,nid))
        if isinstance(node, OpNode):
            for ch in node.children:
                walk(ch,nid)
    walk(root,None)
    return nodes, edges

def _layout(nodes, edges, h_gap=80, v_gap=110, box_w=120, box_h=50):
    children={}
    kids=set()
    for a,b in edges:
        children.setdefault(a,[]).append(b)
        kids.add(b)
    root=[n["id"] for n in nodes if n["id"] not in kids][0] if nodes else None
    widths={}
    def wsub(u):
        ch=children.get(u,[])
        if not ch:
            widths[u]=box_w
            return box_w
        w=0
        for v in ch:
            w+=wsub(v)+h_gap
        w-=h_gap
        widths[u]=max(w,box_w)
        return widths[u]
    if root is None:
        return {}, (400,200), None
    wsub(root)
    pos={}
    def place(u,x_left,y):
        w=widths[u]
        xc=x_left+w/2
        pos[u]=(int(xc-box_w/2), int(y))
        for v in children.get(u,[]):
            place(v, x_left, y+box_h+v_gap)
            x_left+=widths[v]+h_gap
    place(root,20,20)
    W=max(x for x,_ in pos.values())+box_w+20
    H=max(y for _,y in pos.values())+box_h+20
    return pos,(W,H),root

def _svg_escape(s):
    return (s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            .replace('"',"&quot;").replace("'","&apos;"))

def write_svg(nodes, edges, out_path, fill_color="#ffc0cb"):
    """
    Generación del ÁRBOL en SVG.
    """
    pos,(W,H),_=_layout(nodes,edges)
    box_w, box_h = 120, 50
    lines=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">']
    for a,b in edges:
        xa,ya=pos[a]; xb,yb=pos[b]
        ax=xa+box_w//2; ay=ya+box_h
        bx=xb+box_w//2; by=yb
        lines.append(f'<line x1="{ax}" y1="{ay}" x2="{bx}" y2="{by}" stroke="black" stroke-width="2"/>')
        lines.append(f'<polygon points="{bx},{by-6} {bx-5},{by-1} {bx+5},{by-1}" fill="black"/>')
    for n in nodes:
        x,y=pos[n["id"]]; label=_svg_escape(n["label"])
        lines.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" fill="{fill_color}" stroke="black" stroke-width="2" rx="8" ry="8"/>')
        lines.append(f'<text x="{x+box_w/2}" y="{y+box_h/2+5}" text-anchor="middle" font-family="Arial" font-size="14">{label}</text>')
    lines.append('</svg>')
    with open(out_path,"w",encoding="utf-8") as f: 
        f.write("\n".join(lines))

#guardado de reportes
def save_hierarchies_and_reports(TOKENS_info, errores, out_dir="outputs"):
    os.makedirs(out_dir, exist_ok=True)
    trees_dir=os.path.join(out_dir,"trees")
    os.makedirs(trees_dir, exist_ok=True)

    # Depuración jerarquías
    txt_path=os.path.join(out_dir,"jerarquias.txt")
    with open(txt_path,"w",encoding="utf-8") as f:
        for info in TOKENS_info:
            nodes,edges=_collect_tree(info["root"])
            f.write(f"# Operación {info['index']}\nNODES:\n")
            for n in nodes: 
                f.write(f"  {n['id']}: {n['label']}\n")
            f.write("EDGES:\n")
            for a,b in edges: 
                f.write(f"  {a} -> {b}\n")
            f.write("\n")
            #genracion de arboles jerarquicos
            svg_path = os.path.join(out_dir, f"arbol_{info['index']}.svg")
            write_svg(nodes, edges, svg_path, fill_color="#ffc0cb")

    # Operaciones
    op_rows = []
    for info in TOKENS_info:
        svg_rel = f"arbol_{info['index']}.svg"
        arbol_html = f'<a href="{svg_rel}" target="_blank">SVG</a>'

        op_rows.append([
            info["index"],
            info["expr"],
            f"{info['value']:.10g}",
            arbol_html#celda con HTML
        ])

#escribir operaciones.html
    TOKENS_html = html_tabla("Resolución de Operaciones",
                          ["#", "Expresión", "Resultado", "Árbol (link)"],
                          op_rows)
    with open(os.path.join(out_dir, "operaciones.html"), "w", encoding="utf-8") as f:
        f.write(TOKENS_html)
        
    #Errores
    err_rows = [[e["fila"], e["columna"], e["tipo"], (e["lexema"].replace("<","&lt;").replace(">","&gt;"))] for e in errores]
    if not err_rows:
        err_rows=[["—","—","(ninguno)","—"]]
    errs_html = html_tabla("Errores Léxicos", ["Fila","Columna","Tipo","Lexema"], err_rows)
    with open(os.path.join(out_dir,"errores.html"),"w",encoding="utf-8") as f: 
        f.write(errs_html)

    #Resumen General
    resumen_rows = [
        ["Operaciones válidas", str(len(TOKENS_info))],
        ["Errores léxicos", str(len(errores))],
        ["Gráficos por operación", f"{len(TOKENS_info)} SVG"]
    ]
    idx_html = html_tabla("Resumen General", ["Concepto","Valor"], resumen_rows)
    with open(os.path.join(out_dir,"index.html"),"w",encoding="utf-8") as f: 
        f.write(idx_html)

    return {
        "index_html":os.path.join(out_dir,"index.html"),
        "operaciones_html":os.path.join(out_dir,"operaciones.html"),
        "errores_html":os.path.join(out_dir,"errores.html"),
        "jerarquias_txt":txt_path,
        "arboles_dir":trees_dir
    }

#pipeline principal del analizador
def analizar_texto_o_ruta(source_tuple, recolectar_trazas=False, out_dir="outputs"):
    #entrada
    if source_tuple[0] == "file":
        texto = leer_txt(source_tuple[1])
    else:
        texto = source_tuple[1]

    #lexico
    est = crear_estado(texto)
    tokens, errores = analizar(est, recolectar_trazas=recolectar_trazas)

    #parseo → ASTs
    asts_all = parse_all_operations(tokens)

    # combinar errores de parseo (cierre faltante, etc.)
    global _PARSER_ERRORS
    for lexema, tipo, fila, col in _PARSER_ERRORS:
        errores.append(crear_error(lexema, tipo, fila, col))
    _PARSER_ERRORS = []

    #filtro semántico → SOLO VÁLIDAS
    asts_valid = filter_valid_asts(asts_all)

    #evaluación de válidas
    TOKENS_info = evaluate_asts(asts_valid)

    #reportes + árboles SVG
    saved = save_hierarchies_and_reports(TOKENS_info, errores, out_dir=out_dir)

    return tokens, errores, saved

#HOOK PARA LA UI
def run_analyzer(source_tuple, outputs_dir):
    try:
        os.makedirs(outputs_dir, exist_ok=True)
        _, _, _ = analizar_texto_o_ruta(source_tuple, recolectar_trazas=False, out_dir=outputs_dir)
        return True, "Archivos generados"
    except Exception as e:
        return False, str(e)

#INTERFAZ (TKINTER)
class DarkEditor(tkinter.Tk):
    def __init__(self):
        super().__init__()
        self.title("Analizador de Operaciones Aritméticas")
        self.geometry("1100x720")
        self.configure(bg="#2b0f14")
        self.current_filepath = None
        ensure_dirs()
        self._build_ui()

    def _build_ui(self):
        # Barra superior
        top = tkinter.Frame(self, bg="#2b0f14")
        top.pack(side=tkinter.TOP, fill=tkinter.X, padx=18, pady=14)
        btns = [
            ("Abrir Archivo", self.open_file),
            ("Guardar Archivo", self.save_file),
            ("Guardar Como", self.save_file_as),
            ("Analizar Archivo", self.analyze_current_file_or_text),
        ]

        for name, cmd in btns:
            b = tkinter.Button(top, text=name, command=cmd,
                          bg="#9b4b52", fg="#ffffff", activebackground="#b35a60",
                          bd=0, padx=12, pady=8, font=("Arial", 10, "bold"))
            b.pack(side=tkinter.LEFT, padx=8)

        tkinter.Label(top, text="Analizador de Operaciones Aritméticas",
                 bg="#2b0f14", fg="#f3b2bc", font=("Arial", 12, "bold")).pack(side=tkinter.RIGHT, padx=20)

        # Área principal
        main = tkinter.Frame(self, bg="#2b0f14")
        main.pack(fill=tkinter.BOTH, expand=True, padx=18, pady=(0,18))

        # Izquierda: área de texto
        left = tkinter.Frame(main, bg="#2b0f14")
        left.pack(side=tkinter.LEFT, fill=tkinter.BOTH, expand=True)

        text_container = tkinter.Frame(left, bg="#ffffff", bd=2, relief=tkinter.FLAT)
        text_container.pack(fill=tkinter.BOTH, expand=True, padx=(12,8), pady=6)

        self.text_area = scrolledtext.ScrolledText(
            text_container, wrap=tkinter.WORD, font=("Consolas", 12),
            bg="#ffffff", fg="#111111", insertbackground="#111111"
        )
        self.text_area.pack(fill=tkinter.BOTH, expand=True, padx=8, pady=8)

        # Derecha: panel de botones de apertura (docs y outputs)
        right = tkinter.Frame(main, bg="#3a0f16", width=280)
        right.pack(side=tkinter.RIGHT, fill=tkinter.Y, padx=(8,12))

        tkinter.Label(right, text="Documentación", bg="#3a0f16", fg="#f3b2bc", font=("Arial", 12, "bold")).pack(pady=(18,6))
        self._add_right_button(right, "Manual de Usuario", "manual_usuario.pdf")
        self._add_right_button(right, "Manual Técnico", "manual_tecnico.pdf")

        tkinter.Label(right, text="Resultados finales", bg="#3a0f16", fg="#f3b2bc", font=("Arial", 12, "bold")).pack(pady=(18,6))
        self._add_right_button(right, "Resumen General", "index.html", html=True)
        self._add_right_button(right, "Resultados Operaciones", "operaciones.html", html=True)
        self._add_right_button(right, "Errores Léxicos", "errores.html", html=True)

        tkinter.Button(right, text="Ayuda", command=self.help_text,
                  bg="#9b4b52", fg="#ffffff", activebackground="#b35a60", bd=0, padx=12, pady=8).pack(side=tkinter.BOTTOM, pady=24)

        self.status = tkinter.Label(self, text="Nuevo documento", bg="#2b0f14", fg="#f3b2bc", anchor="w")
        self.status.pack(side=tkinter.BOTTOM, fill=tkinter.X)

    def _add_right_button(self, parent, label_text, filename, html=False, image=False):
        frame = tkinter.Frame(parent, bg="#3a0f16")
        frame.pack(fill=tkinter.X, pady=8, padx=14)
        tkinter.Label(frame, text=label_text, bg="#3a0f16", fg="#ffffff", font=("Arial", 10, "bold")).pack(anchor="w")
        btn = tkinter.Button(frame, text="Abrir", command=lambda f=filename: self.open_output_or_doc(f),
                        bg="#9b4b52", fg="#ffffff", activebackground="#b35a60", bd=0, padx=12, pady=6)
        btn.pack(anchor="e", pady=(6,0))

    #archivo abrir/guardar
    def open_file(self):
        path = filedialog.askopenfilename(
            title="Abrir archivo",
            filetypes=[("Text files","*.txt"),("All files","*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.text_area.delete(1.0, tkinter.END)
            self.text_area.insert(tkinter.END, content)
            self.current_filepath = path
            self.status.config(text=f"Abierto: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir el archivo:\n{e}")

    def save_file(self):
        if self.current_filepath:
            try:
                with open(self.current_filepath, "w", encoding="utf-8") as f:
                    f.write(self.text_area.get(1.0, tkinter.END))
                self.status.config(text=f"Guardado: {os.path.basename(self.current_filepath)}")
                messagebox.showinfo("Guardado", "Archivo guardado correctamente.")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo guardar el archivo:\n{e}")
        else:
            self.save_file_as()

    def save_file_as(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files","*.txt"),("All files","*.*")],
            title="Guardar como"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text_area.get(1.0, tkinter.END))
            self.current_filepath = path
            self.status.config(text=f"Guardado: {os.path.basename(path)}")
            messagebox.showinfo("Guardado", "Archivo guardado correctamente.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar el archivo:\n{e}")

    #abrir docs/outputs
    def open_output_or_doc(self, filename):
        path_in_docs = os.path.join(DOCS_DIR, filename)
        path_in_outputs = os.path.join(OUTPUTS_DIR, filename)
        if os.path.exists(path_in_docs):
            path = path_in_docs
        elif os.path.exists(path_in_outputs):
            path = path_in_outputs
        else:
            messagebox.showwarning("No encontrado", f"No se encontró '{filename}' en:\n- {DOCS_DIR}\n- {OUTPUTS_DIR}")
            return
        try:
            url = "file://" + os.path.abspath(path)
            webbrowser.open_new_tab(url)
            self.status.config(text=f"Abierto: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir el archivo:\n{e}")

    #analizar 
    def analyze_current_file_or_text(self):
        if self.current_filepath:
            source = ("file", self.current_filepath)
        else:
            source = ("text", self.text_area.get(1.0, tkinter.END))
        ok, msg = run_analyzer(source, OUTPUTS_DIR)
        if ok:
            messagebox.showinfo("Analizar", "Análisis completado. Archivos generados en 'outputs'.")
            self.status.config(text="Análisis completado")
        else:
            messagebox.showerror("Analizar - Error", f"El analizador falló:\n{msg}")

    #Boton ayuda
    def help_text(self):
        help_text = (
            "Ayuda proporcionada al contactar con:\n\n"
            "-Lizbeth Andrea Herrera Ortega – 1246024\n"
            "-Marcela Nicole Letran Lee – 1102124\n"
        )
        self.text_area.delete(1.0, tkinter.END)
        self.text_area.insert(tkinter.END, help_text)
        self.status.config(text="Mostrando Ayuda")

#nain
if __name__ == "__main__":
    app = DarkEditor()
    app.mainloop()
