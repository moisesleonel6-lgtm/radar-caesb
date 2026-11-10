"""Radar diário de licitações da CAESB (fonte: PNCP).
Gera boletim.html, marca o que é novo (seen.json) e envia por e-mail se SMTP_* estiver configurado."""
import os, re, json, smtplib, html, datetime as dt
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests

CNPJ = "00082024000137"  # CAESB
BASE = "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"

# ---- PERFIL DA EMPRESA CLIENTE (ajuste aqui) ----
PALAVRAS = {"mnd": 15, "pead": 15, "esgoto": 10, "saneamento": 6, "rede": 5,
            "perfuração": 10, "automação": 10, "tubo": 8, "obra": 8, "água": 4}
VALOR_MIN, VALOR_MAX = 500_000, 20_000_000
GO, ATENCAO = 70, 45


def coletar():
    fim = (dt.date.today() + dt.timedelta(days=120)).strftime("%Y%m%d")
    achados = {}
    for mod in range(1, 14):  # todas as modalidades
        pag = 1
        while True:
            try:
                r = requests.get(BASE, timeout=60, params={
                    "dataFinal": fim, "codigoModalidadeContratacao": mod,
                    "cnpj": CNPJ, "pagina": pag, "tamanhoPagina": 50})
            except requests.RequestException:
                break
            if r.status_code != 200:
                break
            d = r.json()
            for c in d.get("data", []):
                if c.get("orgaoEntidade", {}).get("cnpj") == CNPJ:
                    achados[c["numeroControlePNCP"]] = c
            if pag >= d.get("totalPaginas", 1):
                break
            pag += 1
    return list(achados.values())


def analisar(c):
    obj = (c.get("objetoCompra") or "").lower()
    pts = {k: v for k, v in PALAVRAS.items() if k in obj}
    aderencia = min(sum(pts.values()), 50)
    try:
        enc = dt.datetime.fromisoformat(c["dataEncerramentoProposta"][:19])
        dias = (enc - dt.datetime.now()).days
    except Exception:
        enc, dias = None, 0
    prazo = 20 if dias >= 10 else 10 if dias >= 5 else 0
    v = c.get("valorTotalEstimado") or 0
    valor = 15 if VALOR_MIN <= v <= VALOR_MAX else 5 if v == 0 else 0
    eletr = 15 if "eletr" in (c.get("modalidadeNome") or "").lower() else 8
    score = aderencia + prazo + valor + eletr
    rec = "GO" if score >= GO else "ATENÇÃO" if score >= ATENCAO else "NO-GO"
    riscos = []
    if dias < 5: riscos.append("Prazo curto para preparar proposta e habilitação")
    if v == 0: riscos.append("Valor estimado sigiloso ou não informado")
    if v > VALOR_MAX: riscos.append("Valor acima da faixa do perfil: avaliar consórcio")
    if not pts: riscos.append("Objeto sem palavras-chave do perfil")
    return dict(c=c, score=score, rec=rec, dias=dias, enc=enc, pts=list(pts), riscos=riscos, valor=v)


def link(c):
    m = re.match(r"(\d+)-\d+-(\d+)/(\d+)", c["numeroControlePNCP"])
    return f"https://pncp.gov.br/app/editais/{m[1]}/{m[3]}/{int(m[2])}" if m else c.get("linkSistemaOrigem", "#")


def card(a, novo):
    c = a["c"]; cor = {"GO": "#12805c", "ATENÇÃO": "#b7791f", "NO-GO": "#c0392b"}[a["rec"]]
    riscos = "".join(f"<li>{html.escape(r)}</li>" for r in a["riscos"]) or "<li>Sem alertas automáticos</li>"
    return f"""<div style="border:1px solid #dde3ea;border-radius:10px;padding:12px;margin:10px 0;font-family:Arial,sans-serif">
<b style="color:{cor}">{a['rec']} · {a['score']}/100</b>{' · <b>NOVA</b>' if novo else ''}<br>
<b>{html.escape(c.get('modalidadeNome',''))} {c.get('numeroCompra','')}/{c.get('anoCompra','')}</b><br>
{html.escape((c.get('objetoCompra') or '')[:300])}<br>
<small>Valor: R$ {a['valor']:,.2f} · Propostas até: {a['enc'] or 'n/d'} ({a['dias']} dias) · Aderência: {', '.join(a['pts']) or 'nenhuma'}</small>
<ul style="font-size:13px">{riscos}</ul><a href="{link(c)}">Abrir edital no PNCP</a></div>"""


APP = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<link rel="manifest" href="manifest.json"><meta name="theme-color" content="#0b5cab">
<meta name="apple-mobile-web-app-capable" content="yes"><title>Radar CAESB</title>
<style>
:root{--bg:#f5f7fa;--cd:#fff;--tx:#14202e;--mu:#5b6b7c;--ln:#e1e6ec;--ac:#0b5cab;--GO:#12805c;--AT:#b7791f;--NO:#c0392b}
@media(prefers-color-scheme:dark){:root{--bg:#0f1720;--cd:#17212d;--tx:#e8eef5;--mu:#93a4b6;--ln:#2a3a4a;--ac:#5aa7f0;--GO:#4cc79b;--AT:#e5b25a;--NO:#ef7b6e}}
*{box-sizing:border-box}body{margin:0;padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom);background:var(--bg);color:var(--tx);font:15px/1.5 system-ui,sans-serif}
.w{max-width:760px;margin:auto;padding:14px}h1{font-size:19px;margin:0}.mu{color:var(--mu);font-size:12.5px}
.k{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0}.k div{background:var(--cd);border:1px solid var(--ln);border-radius:12px;padding:8px 10px}.k b{display:block;font-size:20px}
.f{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}.f button{border:1px solid var(--ln);background:var(--cd);color:var(--tx);border-radius:99px;padding:6px 12px}.f .on{background:var(--ac);color:#fff}
.c{background:var(--cd);border:1px solid var(--ln);border-radius:14px;padding:13px;margin-bottom:10px}.t{display:flex;justify-content:space-between;gap:8px}
.s{font-weight:700;text-align:center;min-width:56px}.s small{display:block;font-size:10.5px}.g{display:grid;gap:6px;margin:8px 0;font-size:13.5px}
details{border-top:1px solid var(--ln);margin-top:8px;padding-top:6px}summary{color:var(--ac);font-weight:600}a{color:var(--ac)}ul{padding-left:18px;margin:6px 0;font-size:13.5px}
</style></head><body><div class="w"><h1>Radar de Licitações CAESB</h1><div class="mu" id="d"></div>
<div class="k" id="k"></div><div class="f" id="f"></div><div id="l"></div></div>
<script>
var D=__DATA__,F="*",N={GO:"GO","ATENÇÃO":"ATENÇÃO","NO-GO":"NO-GO"},C={GO:"GO","ATENÇÃO":"AT","NO-GO":"NO"};
var R={GO:"Participar: reunir atestados, cotações e montar a proposta.","ATENÇÃO":"Avaliar com cuidado: pode exigir parceiro ou consórcio.","NO-GO":"Não participar: baixa aderência ao perfil."};
function e(s){return String(s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function money(v){return v?"R$ "+v.toLocaleString("pt-BR",{minimumFractionDigits:2}):"Sigiloso/não informado"}
function draw(){var I=D.itens;document.getElementById("d").textContent="Atualizado em "+D.hoje+" · fonte: PNCP";
document.getElementById("k").innerHTML="<div><b>"+I.length+"</b><span class=mu>Em aberto</span></div><div><b>"+I.filter(function(i){return i.novo}).length+"</b><span class=mu>Novas</span></div><div><b>"+I.filter(function(i){return i.rec=="GO"}).length+"</b><span class=mu>GO</span></div>";
document.getElementById("f").innerHTML=["*","GO","ATENÇÃO","NO-GO","NOVAS"].map(function(x){return"<button class='"+(x==F?"on":"")+"' onclick=\\"F='"+x+"';draw()\\">"+(x=="*"?"Todas":x)+"</button>"}).join("");
document.getElementById("l").innerHTML=I.filter(function(i){return F=="*"||F==i.rec||(F=="NOVAS"&&i.novo)}).map(function(i){
return"<div class=c><div class=t><div><b>"+e(i.mod)+" "+e(i.num)+"</b>"+(i.novo?" · <b>NOVA</b>":"")+"<br>"+e(i.obj)+"<div class=mu>"+money(i.valor)+" · propostas até "+e(i.enc||"n/d")+" ("+i.dias+" dias)</div></div><div class=s style='color:var(--"+C[i.rec]+")'>"+i.score+"<small>"+e(i.rec)+"</small></div></div>"+
"<details><summary>Estudo de viabilidade</summary><div class=g><div><b>Aderência ao perfil:</b> "+(i.pts.length?e(i.pts.join(", ")):"nenhuma palavra-chave")+"</div><div><b>Prazo restante:</b> "+i.dias+" dias</div><div><b>Valor estimado:</b> "+money(i.valor)+"</div></div><ul>"+(i.riscos.length?i.riscos.map(function(r){return"<li>"+e(r)+"</li>"}).join(""):"<li>Sem alertas automáticos</li>")+"</ul><div><b>Recomendação:</b> "+R[i.rec]+"</div><p><a href='"+e(i.link)+"' target=_blank>Abrir edital no PNCP</a></p></details></div>"}).join("")||"<p class=mu>Nada nesta categoria.</p>"}
draw()
</script></body></html>"""


def gerar_app(itens, novos, hoje):
    ids = {a["c"]["numeroControlePNCP"] for a in novos}
    dados = [dict(rec=a["rec"], score=a["score"], mod=a["c"].get("modalidadeNome", ""),
                  num=f"{a['c'].get('numeroCompra', '')}/{a['c'].get('anoCompra', '')}",
                  obj=(a["c"].get("objetoCompra") or "")[:400], valor=a["valor"], dias=a["dias"],
                  enc=str(a["enc"] or "")[:16], pts=a["pts"], riscos=a["riscos"], link=link(a["c"]),
                  novo=a["c"]["numeroControlePNCP"] in ids) for a in itens]
    os.makedirs("docs", exist_ok=True)
    js = json.dumps({"hoje": hoje, "itens": dados}, ensure_ascii=False).replace("</", "<\\/")
    open("docs/index.html", "w", encoding="utf-8").write(APP.replace("__DATA__", js))
    json.dump({"name": "Radar CAESB", "short_name": "Radar CAESB", "start_url": ".",
               "display": "standalone", "background_color": "#0f1720", "theme_color": "#0b5cab"},
              open("docs/manifest.json", "w"))


def main():
    seen = set(json.load(open("seen.json"))) if os.path.exists("seen.json") else set()
    itens = sorted((analisar(c) for c in coletar()), key=lambda a: -a["score"])
    novos = [a for a in itens if a["c"]["numeroControlePNCP"] not in seen]
    hoje = dt.date.today().strftime("%d/%m/%Y")
    corpo = f"<h2>Radar de Licitações CAESB · {hoje}</h2><p>{len(itens)} em aberto · {len(novos)} novas · {sum(a['rec']=='GO' for a in itens)} GO</p>"
    corpo += "".join(card(a, a in novos) for a in itens) or "<p>Nenhuma licitação em aberto encontrada.</p>"
    open("boletim.html", "w", encoding="utf-8").write(corpo)
    gerar_app(itens, novos, hoje)
    json.dump(sorted(seen | {a["c"]["numeroControlePNCP"] for a in itens}), open("seen.json", "w"))
    if os.getenv("SMTP_HOST"):
        m = MIMEMultipart("alternative")
        m["Subject"] = f"Radar CAESB {hoje}: {len(novos)} novas"
        m["From"], m["To"] = os.environ["SMTP_USER"], os.environ["EMAIL_TO"]
        m.attach(MIMEText(corpo, "html", "utf-8"))
        with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], 465) as s:
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.sendmail(m["From"], m["To"].split(","), m.as_string())


if __name__ == "__main__":
    main()
