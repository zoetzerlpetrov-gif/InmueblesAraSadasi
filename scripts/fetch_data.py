#!/usr/bin/env python3
"""
fetch_data.py — Actualiza data/developments.json con desarrollos de ARA y SADASI.
Ejecutar: python scripts/fetch_data.py
Requiere: requests, beautifulsoup4
"""

import json
import time
import datetime
import os
import re
import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_FILE = os.path.join(ROOT, 'data', 'developments.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
    'Accept-Language': 'es-MX,es;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# ────────────────────────────────────────────────────────────
# UTILITIES
# ────────────────────────────────────────────────────────────

def get_html(url, timeout=15):
    """Descarga HTML de una URL. Devuelve BeautifulSoup o None si falla."""
    try:
        r = SESSION.get(url, timeout=timeout)
        r.raise_for_status()
        return BeautifulSoup(r.text, 'html.parser')
    except Exception as e:
        print(f'  ⚠ Error fetching {url}: {e}')
        return None

def parse_price(text):
    """Extrae precio entero de strings como '$1,830,202' o '1830202'."""
    if not text:
        return None
    clean = re.sub(r'[^\d]', '', str(text))
    return int(clean) if clean else None


# ────────────────────────────────────────────────────────────
# ARA SCRAPER
# ────────────────────────────────────────────────────────────

ARA_STATES = {
    'estado-de-mexico': ('Estado de México', 19.7, -99.2),
    'ciudad-de-mexico': ('Ciudad de México', 19.43, -99.13),
    'jalisco': ('Jalisco', 20.67, -103.35),
    'nuevo-leon': ('Nuevo León', 25.67, -100.3),
    'tamaulipas': ('Tamaulipas', 26.0, -98.3),
    'hidalgo': ('Hidalgo', 19.83, -98.98),
    'puebla': ('Puebla', 19.04, -98.2),
    'morelos': ('Morelos', 18.83, -99.1),
    'guanajuato': ('Guanajuato', 21.12, -101.68),
    'quintana-roo': ('Quintana Roo', 21.16, -86.85),
    'baja-california': ('Baja California', 32.5, -117.0),
    'guerrero': ('Guerrero', 16.85, -99.85),
    'veracruz': ('Veracruz', 19.17, -96.1),
    'sonora': ('Sonora', 29.07, -110.96),
    'nayarit': ('Nayarit', 21.5, -104.9),
}

def scrape_ara_state(state_slug):
    """Extrae desarrollos y precios de la página informativa de un estado de ARA."""
    url = f'https://ara.com.mx/informacion/{state_slug}'
    soup = get_html(url)
    if not soup:
        return []

    state_name = ARA_STATES.get(state_slug, (state_slug, 0, 0))[0]
    devs = []

    # ARA presenta los desarrollos como secciones con h2/h3 de nombre y tablas/listas de modelos
    # La estructura varía por estado; intentamos encontrar bloques de nombre + precio.
    # Buscamos patrones de precios en pesos: $1,234,567 o similares
    price_re = re.compile(r'\$[\d,]+')

    # Intentar encontrar nombres de desarrollos (h2, h3 con nombres de lugares)
    headings = soup.find_all(['h2', 'h3'])
    for h in headings:
        name = h.get_text(strip=True)
        if not name or len(name) < 4:
            continue
        # Recopilar precios del bloque siguiente
        prices = []
        sibling = h.find_next_sibling()
        for _ in range(10):
            if not sibling:
                break
            txt = sibling.get_text(' ', strip=True)
            found = price_re.findall(txt)
            prices.extend([parse_price(p) for p in found if parse_price(p) and parse_price(p) > 300000])
            sibling = sibling.find_next_sibling()
            if sibling and sibling.name in ['h2', 'h3']:
                break

        if prices:
            devs.append({
                'id': f'ara-{state_slug}-{re.sub(r"[^a-z0-9]", "-", name.lower())}',
                'developer': 'ARA',
                'name': name,
                'city': state_name,
                'state': state_name,
                'lat': ARA_STATES[state_slug][1],
                'lon': ARA_STATES[state_slug][2],
                'precio_min': min(prices),
                'precio_max': max(prices),
                'modelos': [],
                'url': url,
            })

    return devs

def fetch_ara():
    """Recorre todos los estados de ARA y devuelve la lista de desarrollos."""
    print('▶ Scraping ARA...')
    result = []
    for slug in ARA_STATES:
        print(f'  → {slug}')
        devs = scrape_ara_state(slug)
        result.extend(devs)
        time.sleep(1)
    print(f'  ARA total: {len(result)} desarrollos con precio encontrados')
    return result


# ────────────────────────────────────────────────────────────
# SADASI SCRAPER
# ────────────────────────────────────────────────────────────

SADASI_DEV_URLS = [
    ('https://www.sadasi.com/zinacantepec-el-estado-de-mexico/canteras', 'Canteras', 'Zinacantepec', 'Estado de México', 19.275, -99.760),
    ('https://www.sadasi.com/leon-guanajuato/cordillera-residencial', 'Cordillera Residencial', 'León', 'Guanajuato', 21.135, -101.680),
    ('https://www.sadasi.com/puebla-puebla/tres-cantos-residencial', 'Tres Cantos Residencial', 'Puebla', 'Puebla', 19.050, -98.190),
]

def scrape_sadasi_dev(url, name, city, state, lat, lon):
    """Extrae modelos y precios de la página de un desarrollo SADASI."""
    soup = get_html(url)
    if not soup:
        return None

    price_re = re.compile(r'\$[\d,]+')
    prices = []
    modelos = []

    # Buscar tablas o listas con precios
    for row in soup.find_all(['tr', 'li', 'div']):
        txt = row.get_text(' ', strip=True)
        found = price_re.findall(txt)
        parsed = [parse_price(p) for p in found if parse_price(p) and parse_price(p) > 300000]
        if parsed:
            # Intenta extraer nombre de modelo (texto antes del $)
            model_match = re.match(r'^([^$]{4,50})\$', txt)
            model_name = model_match.group(1).strip() if model_match else 'Modelo'
            for p in parsed:
                modelos.append({'nombre': model_name, 'precio': p})
            prices.extend(parsed)

    if not prices:
        return None

    return {
        'id': f'sadasi-{re.sub(r"[^a-z0-9]", "-", name.lower())}',
        'developer': 'SADASI',
        'name': name,
        'city': city,
        'state': state,
        'lat': lat,
        'lon': lon,
        'precio_min': min(prices),
        'precio_max': max(prices),
        'modelos': modelos[:8],
        'url': url,
    }

def fetch_sadasi():
    """Intenta scrapear precios de páginas individuales de SADASI."""
    print('▶ Scraping SADASI...')
    result = []
    for args in SADASI_DEV_URLS:
        url = args[0]
        print(f'  → {args[1]}')
        dev = scrape_sadasi_dev(*args)
        if dev:
            result.append(dev)
        time.sleep(1)
    print(f'  SADASI total: {len(result)} desarrollos con precio encontrados')
    return result


# ────────────────────────────────────────────────────────────
# MERGE CON JSON EXISTENTE
# ────────────────────────────────────────────────────────────

def load_existing():
    if not os.path.exists(OUT_FILE):
        return []
    with open(OUT_FILE, 'r', encoding='utf-8') as f:
        return json.load(f).get('developments', [])

def merge(existing, fresh):
    """
    Combina los datos existentes con los recién scrapeados.
    Los datos frescos actualizan precios; los que no tienen precio nuevo
    conservan el precio anterior.
    """
    fresh_index = {d['id']: d for d in fresh}
    result = []
    seen_ids = set()

    for d in existing:
        if d['id'] in fresh_index:
            updated = dict(d)
            updated.update(fresh_index[d['id']])
            result.append(updated)
        else:
            result.append(d)
        seen_ids.add(d['id'])

    # Agregar desarrollos nuevos no presentes en el JSON existente
    for d in fresh:
        if d['id'] not in seen_ids:
            result.append(d)

    return result

def preserve_if_empty(existing_path, new_data):
    """No sobreescribe si new_data está vacío."""
    if not new_data:
        print('⚠ Sin datos frescos; conservando JSON existente.')
        return
    write_json(new_data)

def write_json(developments):
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    payload = {
        'generated': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'source': 'sadasi.com + ara.com.mx',
        'note': 'Precios en MXN. precio_min es el precio base más bajo. null = sin precio publicado.',
        'developments': developments,
    }
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f'✔ Guardado {len(developments)} desarrollos en {OUT_FILE}')


# ────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────

def main():
    print(f'=== fetch_data.py — {datetime.datetime.utcnow().isoformat()} ===')
    existing = load_existing()
    print(f'  Existentes en JSON: {len(existing)}')

    ara_fresh = fetch_ara()
    sadasi_fresh = fetch_sadasi()
    all_fresh = ara_fresh + sadasi_fresh

    merged = merge(existing, all_fresh)
    preserve_if_empty(OUT_FILE, merged)

if __name__ == '__main__':
    main()
