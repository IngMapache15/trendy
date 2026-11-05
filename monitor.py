"""
Monitor del Calendario de Adviento Trendy 2026
Revisa www.maquillajetrendyshop.com (tienda VTEX) y avisa al celular
cuando el calendario aparezca o quede disponible para la venta.

Notificaciones (configura al menos una como secret en GitHub):
  NTFY_TOPIC         -> nombre del tema en la app ntfy (https://ntfy.sh)
  TELEGRAM_TOKEN     -> token del bot de Telegram (opcional)
  TELEGRAM_CHAT_ID   -> tu chat id de Telegram (opcional)

Otras variables:
  INTERVALO_SEG      -> segundos entre revisiones (default 45)
  DURACION_MIN       -> minutos que corre el loop en cada ejecución (default 65)
  MODO_PRUEBA=1      -> manda una notificación de prueba y hace una sola revisión
"""

import os
import re
import sys
import time
import random
from datetime import datetime, timezone, timedelta

import requests

BASE = "https://www.maquillajetrendyshop.com"
PALABRAS = ["calendario adviento", "adviento", "calendario"]
# Palabras que deben aparecer en el nombre del producto para considerarlo el calendario
FILTRO_NOMBRE = re.compile(r"adviento|calendario", re.I)
# Excluir el calendario de niñas (sale en diciembre, otro producto)
EXCLUIR_NOMBRE = re.compile(r"niñ|nin[ao]s|kids|infantil", re.I)

INTERVALO = int(os.getenv("INTERVALO_SEG", "45"))
DURACION_MIN = int(os.getenv("DURACION_MIN", "65"))
MODO_PRUEBA = os.getenv("MODO_PRUEBA", "0") == "1"

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "").strip()
TG_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "").strip()

BOGOTA = timezone(timedelta(hours=-5))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9",
    "Cache-Control": "no-cache",
}

sesion = requests.Session()
sesion.headers.update(HEADERS)


def ahora():
    return datetime.now(BOGOTA).strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    print(f"[{ahora()}] {msg}", flush=True)


# ----------------------------------------------------------------- avisos
def notificar(titulo, mensaje, url=None, urgente=True):
    enviado = False
    if NTFY_TOPIC:
        try:
            h = {
                "Title": titulo.encode("utf-8"),
                "Priority": "urgent" if urgente else "default",
                "Tags": "rotating_light,lipstick" if urgente else "white_check_mark",
            }
            if url:
                h["Click"] = url
                h["Actions"] = f"view, Abrir tienda, {url}"
            r = requests.post(f"https://ntfy.sh/{NTFY_TOPIC}",
                              data=mensaje.encode("utf-8"), headers=h, timeout=15)
            log(f"ntfy -> {r.status_code}")
            enviado = enviado or r.ok
        except Exception as e:
            log(f"ntfy error: {e}")
    if TG_TOKEN and TG_CHAT:
        try:
            texto = f"{titulo}\n\n{mensaje}" + (f"\n{url}" if url else "")
            r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                              json={"chat_id": TG_CHAT, "text": texto,
                                    "disable_web_page_preview": False},
                              timeout=15)
            log(f"telegram -> {r.status_code}")
            enviado = enviado or r.ok
        except Exception as e:
            log(f"telegram error: {e}")
    if not enviado:
        log("ADVERTENCIA: no se pudo enviar ninguna notificación "
            "(¿configuraste NTFY_TOPIC o TELEGRAM_*?)")
    return enviado


# ----------------------------------------------------------------- revisiones
def _get(url, **kw):
    # parámetro aleatorio para saltar caché del CDN
    sep = "&" if "?" in url else "?"
    return sesion.get(f"{url}{sep}_nc={random.randint(1, 10**9)}", timeout=20, **kw)


def analizar_productos(productos):
    """Recibe la lista JSON de productos VTEX y devuelve los que son el calendario."""
    hallados = []
    for p in productos or []:
        nombre = p.get("productName") or p.get("productTitle") or ""
        if not FILTRO_NOMBRE.search(nombre) or EXCLUIR_NOMBRE.search(nombre):
            continue
        link = p.get("link") or ""
        if link.startswith("/"):
            link = BASE + link
        if not link and p.get("linkText"):
            link = f"{BASE}/{p['linkText']}/p"
        disponible, cantidad, precio = False, 0, None
        for item in p.get("items", []):
            for s in item.get("sellers", []):
                o = s.get("commertialOffer", {}) or {}
                q = o.get("AvailableQuantity", 0) or 0
                if o.get("IsAvailable") or q > 0:
                    disponible = True
                cantidad = max(cantidad, q)
                if o.get("Price"):
                    precio = o.get("Price")
        hallados.append({"nombre": nombre, "link": link or BASE,
                         "disponible": disponible, "cantidad": cantidad,
                         "precio": precio})
    return hallados


def revisar_catalogo():
    """API pública del catálogo VTEX."""
    resultados = {}
    for palabra in PALABRAS:
        try:
            r = _get(f"{BASE}/api/catalog_system/pub/products/search",
                     params={"ft": palabra, "_from": 0, "_to": 49})
            if r.status_code in (200, 206):
                for h in analizar_productos(r.json()):
                    resultados[h["link"]] = h
            else:
                log(f"catálogo '{palabra}' -> HTTP {r.status_code}")
        except Exception as e:
            log(f"catálogo '{palabra}' error: {e}")
    return list(resultados.values())


def revisar_intelligent_search():
    """Buscador de VTEX IO (respaldo; a veces indexa antes o después)."""
    try:
        r = _get(f"{BASE}/api/io/_v/api/intelligent-search/product_search/",
                 params={"query": "calendario adviento", "count": 50,
                         "hideUnavailableItems": "false"})
        if r.ok:
            return analizar_productos(r.json().get("products", []))
        log(f"intelligent-search -> HTTP {r.status_code}")
    except Exception as e:
        log(f"intelligent-search error: {e}")
    return []


def revisar_home():
    """Busca 'adviento' en la página principal (banner o enlace de lanzamiento)."""
    try:
        r = _get(BASE + "/")
        if r.ok:
            html = r.text.lower()
            # El footer ya trae 'terminos-calendario-2026', así que buscamos 'adviento'
            enlaces = re.findall(r'href="([^"]*adviento[^"]*)"', html)
            return ("adviento" in html), enlaces
        log(f"home -> HTTP {r.status_code}")
    except Exception as e:
        log(f"home error: {e}")
    return False, []


# ----------------------------------------------------------------- loop
def main():
    if not (NTFY_TOPIC or (TG_TOKEN and TG_CHAT)):
        log("Falta configurar NTFY_TOPIC o TELEGRAM_TOKEN + TELEGRAM_CHAT_ID")
        sys.exit(1)

    if MODO_PRUEBA:
        notificar("✅ Monitor Trendy activo",
                  "Prueba OK. Te avisaré apenas el calendario de adviento salga a la venta.",
                  BASE, urgente=False)

    fin = time.time() + DURACION_MIN * 60
    visto_producto = set()      # productos ya avisados como "apareció"
    avisos_venta = {}           # link -> nº de avisos de venta enviados
    ultimo_aviso_venta = {}     # link -> timestamp
    home_avisada = False
    ciclo = 0

    while True:
        ciclo += 1
        hallados = {h["link"]: h for h in revisar_catalogo()}
        for h in revisar_intelligent_search():
            # combinar: si cualquiera dice disponible, cuenta como disponible
            if h["link"] in hallados:
                hallados[h["link"]]["disponible"] |= h["disponible"]
            else:
                hallados[h["link"]] = h
        hay_adviento_home, enlaces_home = revisar_home()

        resumen = ", ".join(
            f"{h['nombre']} [{'DISPONIBLE' if h['disponible'] else 'no disp.'}]"
            for h in hallados.values()) or "sin productos de calendario"
        log(f"ciclo {ciclo}: {resumen} | home 'adviento': {hay_adviento_home}")

        for link, h in hallados.items():
            precio = f" — ${h['precio']:,.0f}".replace(",", ".") if h["precio"] else ""
            if h["disponible"]:
                n = avisos_venta.get(link, 0)
                ultimo = ultimo_aviso_venta.get(link, 0)
                # 5 avisos seguidos y luego uno cada 10 min, para que no se te pase
                if n < 5 or time.time() - ultimo > 600:
                    notificar("🚨 ¡CALENDARIO TRENDY A LA VENTA!",
                              f"{h['nombre']}{precio}\nEntra YA y compra. "
                              f"Pago: tarjeta o PSE.", link, urgente=True)
                    avisos_venta[link] = n + 1
                    ultimo_aviso_venta[link] = time.time()
            elif link not in visto_producto:
                notificar("👀 Apareció el calendario en la tienda",
                          f"{h['nombre']}{precio}\nAún no está disponible, "
                          f"pero ya está publicado. Atento.", link, urgente=True)
                visto_producto.add(link)

        if hay_adviento_home and not home_avisada:
            destino = enlaces_home[0] if enlaces_home else BASE
            if destino.startswith("/"):
                destino = BASE + destino
            notificar("👀 'Adviento' apareció en la página de Trendy",
                      "La home ya menciona el calendario de adviento. Revisa ahora.",
                      destino, urgente=True)
            home_avisada = True

        if MODO_PRUEBA or time.time() + INTERVALO > fin:
            break
        time.sleep(INTERVALO + random.uniform(-5, 5))

    log("Fin de esta ejecución.")


if __name__ == "__main__":
    main()
