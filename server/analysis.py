import json, re, requests
import numpy as np
import config

# score = weighted pieces, each 0-100. Only pH, turbidity and temperature exist: no chlorine, TDS or bacteria.
def score(r):
    parts = {}
    if r.get("ph") is not None:
        parts["ph"] = float(np.interp(r["ph"], [4.5, 6.5, 8.5, 10.5], [0, 100, 100, 0]))
    if r.get("turb_ntu") is not None:
        parts["turb"] = float(np.interp(r["turb_ntu"], [1, 5, 50], [100, 70, 0]))
    if r.get("temp_c") is not None:
        parts["temp"] = float(np.interp(r["temp_c"], [25, 35, 45], [100, 50, 0]))
    w = {"ph": .4, "turb": .45, "temp": .15}
    if not parts:
        return None, parts
    s = sum(parts[k] * w[k] for k in parts) / sum(w[k] for k in parts)
    if min(parts.values()) < 20:
        s = min(s, 40)
    return round(s), {k: round(v) for k, v in parts.items()}

def patterns(rows):
    """Recurring problems over the given history, in plain counts."""
    out = []
    if len(rows) < 3:
        return out
    def frac(f):
        xs = [r for r in rows if f(r)]
        return len(xs) / len(rows)
    for label, f in [("pH ácido (<6.5)", lambda r: r["ph"] is not None and r["ph"] < 6.5),
                     ("pH alcalino (>8.5)", lambda r: r["ph"] is not None and r["ph"] > 8.5),
                     ("agua turbia (>5 NTU)", lambda r: r["ntu"] is not None and r["ntu"] > 5),
                     ("agua tibia (>28 °C)", lambda r: r["temp"] is not None and r["temp"] > 28)]:
        p = frac(f)
        if p >= .25:
            out.append({"issue": label, "share": round(p * 100)})
    return out

def rule_based(r):
    """Fallback when the LLM is unavailable: never leave the UI empty."""
    issues, actions = [], []
    ph, ntu = r.get("ph"), r.get("turb_ntu")
    if ph is not None and ph < 6.5:
        issues.append(f"El agua es ácida (pH {ph:.1f}).")
        actions.append({"what": "Subir el pH", "product": "Bicarbonato de sodio o carbonato de sodio (soda ash)", "dose": "Poco a poco, midiendo de nuevo"})
    elif ph is not None and ph > 8.5:
        issues.append(f"El agua es alcalina (pH {ph:.1f}).")
        actions.append({"what": "Bajar el pH", "product": "Ácido cítrico grado alimenticio o bisulfato de sodio", "dose": "Poco a poco, midiendo de nuevo"})
    if ntu is not None and ntu > 5:
        issues.append(f"El agua está turbia ({ntu:.0f} NTU): hay sedimento o materia suspendida.")
        actions.append({"what": "Aclarar el agua", "product": "Filtro de sedimentos de 5 micras; limpiar el tinaco", "dose": ""})
    if not issues:
        issues.append("Las lecturas están dentro de lo normal.")
    return {"headline": issues[0], "summary": " ".join(issues), "issues": issues, "actions": actions,
            "sources": [], "model": "reglas (sin LLM)"}

# ---- web tools for the model ----
def _search(query):
    from ddgs import DDGS
    hits = DDGS().text(query, max_results=4, region="mx-es")
    return json.dumps([{"title": h["title"], "url": h["href"], "snippet": h["body"][:300]} for h in hits], ensure_ascii=False)

def _read(url):
    t = requests.get(url, timeout=15, headers={"User-Agent": "ALCI/1.0"}).text
    t = re.sub(r"(?s)<(script|style|nav|footer)[^>]*>.*?</\1>", " ", t)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))[:2500]

TOOLS = [
    {"type": "function", "function": {"name": "web_search", "description": "Busca en la web (preferir OMS, EPA, CONAGUA, universidades).",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "read_page", "description": "Lee el texto de una página.",
     "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
]
FN = {"web_search": lambda a: _search(a["query"]), "read_page": lambda a: _read(a["url"])}

SYSTEM = """Eres ALCI, asistente de calidad del agua para colonias de México. Recibes lecturas de un sensor de pH, uno de turbidez (NTU) y uno de temperatura.
Solo medimos esos tres parámetros: no hay cloro, sólidos disueltos ni bacterias. Dilo cuando sea relevante y nunca digas que el agua es o no es 'potable', 'apta' o 'segura': describe su estado y qué corregir.
No inventes URLs: cita solo las que te devolvió web_search.
Si el pH dice 'sin calibrar' trátalo como aproximado.
Si necesitas datos confiables (rangos NOM-127-SSA1, OMS, EPA, dosis de productos), usa web_search y cita la URL.
Español sencillo para vecinos, sin tecnicismos. Sugiere productos concretos y accesibles con dosis prudentes, y avisa cuando conviene un laboratorio."""

SCHEMA = {"type": "object", "required": ["headline", "summary", "issues", "actions", "sources"], "properties": {
    "headline": {"type": "string", "description": "describe el estado del agua en máximo 10 palabras, ej: 'Agua ácida y algo turbia'"},
    "summary": {"type": "string", "description": "2-4 frases: qué le pasa al agua"},
    "issues": {"type": "array", "items": {"type": "string"}},
    "actions": {"type": "array", "items": {"type": "object", "required": ["what", "product", "dose"],
                "properties": {"what": {"type": "string"}, "product": {"type": "string"}, "dose": {"type": "string"}}}},
    "sources": {"type": "array", "items": {"type": "string"}}}}

def _chat(messages, **kw):
    r = requests.post(f"{config.OLLAMA_URL}/api/chat", timeout=1200, json={
        "model": config.MODEL, "messages": messages, "stream": False, "think": False,
        "options": {"num_ctx": 6144, "temperature": 0.3}, **kw})
    r.raise_for_status()
    return r.json()["message"]

def llm_analysis(r, sc, parts, recurring):
    desc = (f"pH: {r.get('ph'):.2f}{'' if r.get('ph_calibrated') else ' (sin calibrar)'}\n" if r.get("ph") is not None else "pH: sin dato\n")
    desc += f"Turbidez: {r['turb_ntu']:.1f} NTU\n" if r.get("turb_ntu") is not None else "Turbidez: sin dato\n"
    desc += f"Temperatura: {r['temp_c']:.1f} °C\n" if r.get("temp_c") is not None else "Temperatura: sin dato\n"
    desc += f"Puntaje: {sc}/100 {parts}\n"
    if recurring:
        desc += "Problemas recurrentes en el historial: " + "; ".join(f"{p['issue']} en {p['share']}% de las muestras" for p in recurring) + "\n"
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "Muestra analizada:\n" + desc}]
    seen = set()  # only URLs the tools really returned may be cited
    for _ in range(3):  # bounded research loop
        m = _chat(msgs, tools=TOOLS)
        msgs.append(m)
        if not m.get("tool_calls"):
            break
        for tc in m["tool_calls"]:
            f = tc["function"]
            try:
                res = FN[f["name"]](f["arguments"])
            except Exception as e:
                res = f"error: {e}"
            seen.update(re.findall(r"https?://[^\s\"'<>]+", res))
            if f["name"] == "read_page":
                seen.add(f["arguments"].get("url"))
            msgs.append({"role": "tool", "tool_name": f["name"], "content": res})
    msgs.append({"role": "user", "content": "Ahora entrega el informe final en el formato pedido."})
    out = json.loads(_chat(msgs, format=SCHEMA)["content"])
    out["sources"] = [u for u in out.get("sources", []) if u in seen]
    out["model"] = config.MODEL
    return out

def analyze(r, sc, parts, recurring):
    try:
        return llm_analysis(r, sc, parts, recurring)
    except Exception as e:
        out = rule_based(r)
        out["llm_error"] = str(e)[:200]
        return out
