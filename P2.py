import os
import sys

#lectura archivo entrada
def leer_txt(ruta):
    with open(ruta, "r", encoding="utf-8") as f:
        return f.read()

# token/errores (diccionarios)
def crear_token(tipo, lexema, fila, columna, valor=None):
    return {"tipo": tipo, "lexema": lexema, "fila": fila, "columna": columna, "valor": valor}

def crear_error(lexema, tipo, fila, columna):
    return {"lexema": lexema, "tipo": tipo, "fila": fila, "columna": columna}

#carACTERES
def es_digito(caracter):
    if caracter is None:
        return False
    if caracter >= '0' and caracter <= '9':
        return True
    else:
        return False

def es_espacio(c):
    return c in ' \t\r\n'

#estado scanner
def crear_estado(texto):
    return {
        "texto": texto,
        "i": 0,
        "fila": 1,
        "col": 1,
        "n": len(texto),
        "tokens": [],
        "errores": []
    }

def mirar(estado):
    posicion_actual = estado["i"]
    if posicion_actual < estado["n"]:
        return estado["texto"][posicion_actual]
    else:
        return None


def avanzar(estado):
    caracter_actual = mirar(estado)
    if caracter_actual is None:
        return None
    estado["i"] += 1
    if caracter_actual == '\n':
        estado["fila"] += 1
        estado["col"] = 1
    else:
        estado["col"] += 1
    return caracter_actual


def agregar_error(estado, lexema, tipo, fila=None, columna=None):
    if fila is None:
        fila = estado["fila"]
    if columna is None:
        columna = estado["col"]
    error = crear_error(lexema, tipo, fila, columna)
    estado["errores"].append(error)


def consumir_while(estado, condicion):
    buffer = []

    while True:

        c = mirar(estado)
        if c is None:
            break
        if not condicion(c):
            break
        consumido = avanzar(estado)
        buffer.append(consumido)
    return ''.join(buffer)


#leer etiqueta
def lexetiqueta_en_bruto(estado):
    assert mirar(estado) == '<'
    start_f, start_c = estado["fila"], estado["col"]
    buf = []
    buf.append(avanzar(estado)) #<
    while True:
        c = mirar(estado)
        if c is None:
            lex = ''.join(buf)
            agregar_error(estado, lex, "EtiquetaNoCerrada", start_f, start_c)
            return None, start_f, start_c
        if c == '>':
            buf.append(avanzar(estado))
            break
        buf.append(avanzar(estado))
    return ''.join(buf), start_f, start_c


def extraer_hasta_cierre(estado, nombre_cierre):
    fila_inicio = estado["fila"]
    col_inicio = estado["col"]
    partes = []

    while True:
        c = mirar(estado)
        if c is None:
            contenido_leido = ''.join(partes)
            agregar_error(estado, contenido_leido, "CierreNoEncontrado", fila_inicio, col_inicio)
            return None, None, None
        if c == '<':
            en_bruto, fila_token, col_token = lexetiqueta_en_bruto(estado)

            if en_bruto is None:
                return None, None, None

            inner = en_bruto[1:-1].strip()

            if inner.startswith('/') and inner[1:].strip().upper() == nombre_cierre.upper():
                return ''.join(partes), fila_token, col_token
            else:
                partes.append(en_bruto)
                continue
        partes.append(avanzar(estado))


# manejo etiqueta abierta (operacion)
def procesar_operacion_apertura(estado, inner, fila, col):
    rest = inner[len('OPERACION'):].strip()
    if rest.startswith('='):
        nombre = rest[1:].strip().split()[0] if rest[1:].strip() else ''
        nombre_up = nombre.upper()
        valid_ops = {"SUMA","RESTA","MULTIPLICACION","DIVISION","POTENCIA","RAIZ","INVERSO","MOD"}
        if nombre_up in valid_ops:
            estado["tokens"].append(crear_token("OPEN_OPERACION", f"<Operacion= {nombre_up}>", fila, col, valor=nombre_up))
            return
        else:
            agregar_error(estado, f"<Operacion{rest}>", "NombreOperacionInvalido", fila, col)
            return
    else:
        agregar_error(estado, f"<Operacion{rest}>", "FormatoOperacionInvalido", fila, col)
        return

# scanner
def escanear(texto):
    estado = crear_estado(texto)
    while True:
        c = mirar(estado)
        if c is None:
            break
        if c in ' \t\r\n':
            avanzar(estado)
            continue
        if c == '<':
            en_bruto, rf, rc = lexetiqueta_en_bruto(estado)
            if en_bruto is None:
                continue
            inner = en_bruto[1:-1].strip()
            up = inner.upper()
            if up.startswith('/'):
                name = up[1:].strip()
                if name == 'OPERACION':
                    estado["tokens"].append(crear_token("CLOSE_OPERACION", en_bruto, rf, rc))
                elif name == 'NUMERO':
                    estado["tokens"].append(crear_token("CLOSE_NUMERO", en_bruto, rf, rc))
                elif name == 'P':
                    estado["tokens"].append(crear_token("CLOSE_P", en_bruto, rf, rc))
                elif name == 'R':
                    estado["tokens"].append(crear_token("CLOSE_R", en_bruto, rf, rc))
                else:
                    agregar_error(estado, en_bruto, "CierreEtiquetaDesconocido", rf, rc)
                continue

            # Apertura OPERACION
            if up.startswith('OPERACION'):
                procesar_operacion_apertura(estado, inner, rf, rc)
                continue

            # Apertura NUMERO -> </Numero>, validar como numero
            if up == 'NUMERO':
                contenido, cierre_f, cierre_c = extraer_hasta_cierre(estado, 'Numero')
                if contenido is None:
                    continue 
                # limpiar
                valor = contenido.strip()
                # valido entero positivo negativo decimal
                if valor == '':
                    agregar_error(estado, "<Numero> vacío", "NumeroVacio", rf, rc)
                else:
                    if validar_numero_formato(valor):
                        estado["tokens"].append(crear_token("NUMBER", valor, rf, rc, valor=valor))
                    else:
                        agregar_error(estado, valor, "NumeroInvalido", rf, rc)
                continue

            # Apertura P -> </P> y validar entero no negativo
            if up == 'P':
                contenido, cierre_f, cierre_c = extraer_hasta_cierre(estado, 'P')
                if contenido is None:
                    continue
                valor = contenido.strip()
                if validar_entero_formato(valor):
                    estado["tokens"].append(crear_token("P_VAL", valor, rf, rc, valor=valor))
                else:
                    agregar_error(estado, valor, "PInvalido", rf, rc)
                continue

            # Apertura R -> </R> y validar entero positivo
            if up == 'R':
                contenido, cierre_f, cierre_c = extraer_hasta_cierre(estado, 'R')
                if contenido is None:
                    continue
                valor = contenido.strip()
                if validar_entero_formato(valor):
                    estado["tokens"].append(crear_token("R_VAL", valor, rf, rc, valor=valor))
                else:
                    agregar_error(estado, valor, "RInvalido", rf, rc)
                continue

            # cualquier otra etiqueta desconocida
            agregar_error(estado, en_bruto, "EtiquetaDesconocida", rf, rc)
            continue

        # si  numeros fuera de etiquetas error
        if es_digito(c) or c in '+-.':
            start_f, start_c = estado["fila"], estado["col"]
            val = consumir_while(estado, lambda ch: ch is not None and (es_digito(ch) or ch in '+-.'))
            estado["errores"].append(crear_error(val, "ValorFueraEtiqueta", start_f, start_c))
            continue

        # caarcter no validado
        start_f, start_c = estado["fila"], estado["col"]
        bad = avanzar(estado)
        agregar_error(estado, bad or '', "CaracterInvalido", start_f, start_c)
    return estado["tokens"], estado["errores"]

# validar numero 
def validar_numero_formato(s):
    if s is None or s == '':
        return False
    i = 0
    if s[0] in '+-':
        i = 1
    if i >= len(s):
        return False
    tiene_punto = False
    digitos_antes = 0
    digitos_despues = 0
    for ch in s[i:]:
        if ch == '.':
            if tiene_punto:
                return False
            tiene_punto = True
            continue
        if not ('0' <= ch <= '9'):
            return False
        if not tiene_punto:
            digitos_antes += 1
        else:
            digitos_despues += 1
    if tiene_punto:
        return (digitos_antes >= 1 and digitos_despues >= 1)
    else:
        return (digitos_antes >= 1)

def validar_entero_formato(s):
    if s is None or s == '':
        return False
    i = 0
    if s[0] in '+-':
        i = 1
    if i >= len(s):
        return False
    for ch in s[i:]:
        if not ('0' <= ch <= '9'):
            return False
    return True

#minimo dos operadores de token numero
def validar_operandos_minimos(tokens, errores_lex):
    errores = list(errores_lex)
    i = 0
    L = len(tokens)
    while i < L:
        tk = tokens[i]
        if tk["tipo"] == "OPEN_OPERACION":
            niveles = 0
            j = i + 1
            operandos = 0
            while j < L:
                t = tokens[j]
                if t["tipo"] == "OPEN_OPERACION":
                    niveles += 1
                    operandos += 1
                    j += 1
                    continue
                if t["tipo"] == "CLOSE_OPERACION":
                    if niveles == 0:
                        break  # cierre de la operación 
                    else:
                        niveles -= 1
                        j += 1
                        continue
                if t["tipo"] in ("NUMBER", "P_VAL", "R_VAL"):
                    operandos += 1
                    j += 1
                    continue
                j += 1
            # j o fin
            if operandos < 2:
                errores.append(crear_error(tk["lexema"], "OperacionConMenosDeDosOperandos", tk["fila"], tk["columna"]))
            i = j
        else:
            i += 1
    return errores

#integrara analizador
def analizar_documento(ruta):
    texto = leer_txt(ruta)
    tokens, errores_lex = escanear(texto)
    errores_totales = validar_operandos_minimos(tokens, errores_lex)
    return tokens, errores_totales

#main
if __name__ == "__main__":
    print("Trabajo en:", os.getcwd())
    print("Archivos:", os.listdir("."))
    if len(sys.argv) >= 2:
        ruta = sys.argv[1]
    else:
        ruta = "pruebas.txt"
    try:
        tokens, errores = analizar_documento(ruta)
    except FileNotFoundError:
        print(f"Archivo no encontrado: {ruta}")
        sys.exit(1)

    print("\nTokens reconocidos:")
    for t in tokens:
        print(" ", t)
    print("\nErrores léxicos:")
    for e in errores:
        print(" ", e)
        ruta = "pruebas.txt"
    tokens, errores = analizar_documento(ruta)
