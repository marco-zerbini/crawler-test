from bs4 import BeautifulSoup
from jinja2 import Template
import os
import re

# === CONFIG ===
ISO_CODE = input("Inserisci il codice ISO-3 del paese (es. 'usa', 'jpn'): ").lower()

INPUT_DIR = 'input'
TEMPLATE_PATH = 'templates/template.html'
OUTPUT_DIR = f'docs/{ISO_CODE}'
GLOBAL_INDEX_PATH = 'docs/index-global.html'

# === FUNZIONE PER ESTRARRE SEZIONI PER TITOLO H2 ===
def estrai_blocco_per_titolo(soup, titolo):
    blocchi = soup.find_all('h2')
    for h2 in blocchi:
        if titolo.lower() in h2.get_text(strip=True).lower():
            container = h2.find_parent()
            if container:
                testo = '\n'.join(p.get_text(strip=True) for p in container.find_all('p'))
                return testo
    return 'Contenuto non trovato'

# === PREPARAZIONE TEMPLATE ===
with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
    template = Template(f.read())

# === ASSICURA CHE LA DESTINAZIONE ESISTA ===
os.makedirs(OUTPUT_DIR, exist_ok=True)

# === CICLO SU TUTTI I FILE IN /input ===
for filename in os.listdir(INPUT_DIR):
    if filename.endswith('.html'):
        path = os.path.join(INPUT_DIR, filename)
        with open(path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')

        title = soup.title.string.strip() if soup.title else 'viaggio'
        slug = re.sub(r'[^\w\s-]', '', title.lower())
        slug = re.sub(r'\s+', '-', slug).strip('-')
        output_filename = f'{slug}.html'
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        # Estrazione contenuti
        content = {
            'title': title,
            'heading': title,
            'summary': soup.find('div', class_='long-description').get_text(strip=True) if soup.find('div', class_='long-description') else 'Contenuto non trovato',
            'mood': estrai_blocco_per_titolo(soup, 'Mood di viaggio'),
            'physical_effort': estrai_blocco_per_titolo(soup, 'Impegno fisico'),
            'travel_requirements': estrai_blocco_per_titolo(soup, 'Cosa serve'),
            'meeting_info': estrai_blocco_per_titolo(soup, 'Ritrovo'),
        }

        # Rendering e scrittura HTML finale
        rendered_html = template.render(**content)
        with open(output_path, 'w', encoding='utf-8') as out:
            out.write(rendered_html)
        print(f"✅ Creato file: {output_path}")

        # Aggiorna index nazionale
        national_index_path = os.path.join(OUTPUT_DIR, 'index.html')
        national_link = f'<li><a href="{output_filename}">{title}</a></li>\n'
        if os.path.exists(national_index_path):
            with open(national_index_path, 'r', encoding='utf-8') as f:
                index_content = f.read()
            if national_link not in index_content:
                index_content = index_content.replace('</ul>', national_link + '</ul>')
        else:
            index_content = f"""<!DOCTYPE html>
<html lang="it">
<head><meta charset="UTF-8"><title>Viaggi in {ISO_CODE.upper()}</title></head>
<body>
<h1>Viaggi in {ISO_CODE.upper()}</h1>
<ul>{national_link}</ul>
</body></html>"""

        with open(national_index_path, 'w', encoding='utf-8') as f:
            f.write(index_content)
        print(f"📘 Index {ISO_CODE} aggiornato.")

        # Aggiorna index globale
        global_link = f'<li><a href="{ISO_CODE}/index.html">Viaggi in {ISO_CODE.upper()}</a></li>\n'
        if os.path.exists(GLOBAL_INDEX_PATH):
            with open(GLOBAL_INDEX_PATH, 'r', encoding='utf-8') as f:
                global_content = f.read()
            if global_link not in global_content:
                global_content = global_content.replace('</ul>', global_link + '</ul>')
        else:
            global_content = f"""<!DOCTYPE html>
<html lang="it">
<head><meta charset="UTF-8"><title>Index globale WeRoad</title></head>
<body>
<h1>Index globale - Viaggi per nazione</h1>
<ul>{global_link}</ul>
</body></html>"""

        with open(GLOBAL_INDEX_PATH, 'w', encoding='utf-8') as f:
            f.write(global_content)
        print("🌍 Index globale aggiornato.")

import subprocess

# === Git: aggiunge e committa i cambiamenti ===
try:
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", f"Aggiunto/aggiornato viaggio {title}"], check=True)
    subprocess.run(["git", "push"], check=True)
    print("🚀 Modifiche pubblicate su GitHub!")
except subprocess.CalledProcessError as e:
    print("⚠️ Errore durante l'esecuzione dei comandi Git:", e)
