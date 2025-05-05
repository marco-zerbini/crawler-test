# weroad_trip_generator.py
import asyncio
import os
import re
import subprocess
from pathlib import Path
from bs4 import BeautifulSoup
from jinja2 import Template
from playwright.async_api import async_playwright

# === CONFIG ===
ISO_CODE = input("Inserisci il codice ISO-3 del paese (es. 'usa', 'jpn'): ").lower()
INPUT_URLS_PATH = 'input/urls.txt'
TEMPLATE_PATH = 'templates/template.html'
OUTPUT_DIR = f'docs/{ISO_CODE}'
GLOBAL_INDEX_PATH = 'docs/index.html'

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs("input", exist_ok=True)

# === UTIL ===
def slugify(url):
    name = url.strip().split("/")[-1]
    slug = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"\s+", "-", slug).strip("-")
    return slug

# === FUNZIONE PER ESTRARRE HTML DA URL ===
async def estrai_html_con_playwright(url, output_file):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=200)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.evaluate("document.documentElement.style.zoom = '0.7'")
        except Exception as e:
            print(f"❌ Errore caricamento {url}: {e}")
            return

        try:
            await page.evaluate("""
                () => {
                    const el = document.getElementById('iubenda-cs-banner');
                    if (el) el.remove();
                }
            """)
        except:
            pass

        try:
            accordion_icons = await page.locator('[data-testid="accordion-icon"]').all()
            for icon in accordion_icons:
                try:
                    await icon.click()
                    await page.wait_for_timeout(200)
                except:
                    pass
        except:
            pass

        try:
            await page.evaluate("""
                () => {
                    const el = [...document.querySelectorAll('div.flex')]
                        .find(el => el.innerText.includes('Cassa comune'));
                    if (el) el.click();
                }
            """)
            await page.wait_for_timeout(3000)
        except:
            print("⚠️ Impossibile cliccare su 'Cassa comune'")

        html = await page.content()
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html)
        await browser.close()

# === ESTRAZIONE DATI DAL DOM ===
def estrai_blocco_per_titolo(soup, titolo):
    blocchi = soup.find_all('h2')
    for h2 in blocchi:
        if titolo.lower() in h2.get_text(strip=True).lower():
            container = h2.find_parent()
            if container:
                testo = '\n'.join(p.get_text(strip=True) for p in container.find_all('p'))
                return testo
    return 'Contenuto non trovato'

def estrai_itinerario(soup):
    giorni = soup.select("div[data-name='accordion-header']")
    blocchi = []
    for giorno in giorni:
        try:
            numero = giorno.select_one("span").get_text(strip=True)
            titolo = giorno.find_next("h4").get_text(strip=True)
            descrizione = []
            container = giorno.find_parent().find_next_sibling("div")
            if container:
                desc_block = container.select_one("div.description.content")
                if desc_block:
                    for p in desc_block.find_all("p"):
                        testo = p.get_text(strip=True)
                        if testo:
                            descrizione.append(f"<p>{testo}</p>")
                info_block = container.select_one("div.info")
                if info_block:
                    for p in info_block.find_all("p"):
                        descrizione.append(f"<p>{p.decode_contents()}</p>")
            blocco_html = f"""
<section class=\"giorno\">
  <h3>Giorno {numero}: {titolo}</h3>
  {''.join(descrizione)}
</section>"""
            blocchi.append(blocco_html)
        except:
            continue
    return "\n".join(blocchi)

def estrai_modale_formattata(soup):
    modal = soup.select_one("div.wr-modal-external-container")
    if not modal:
        return ("", "", "", "")
    sezioni = {"Cosa è incluso": "", "La quota viaggio non comprende": "", "La quota della cassa comune comprende": "", "Info aggiuntive": ""}
    current = None
    for el in modal.find_all(recursive=False):
        if el.name == "h2" and el.get_text(strip=True) in sezioni:
            current = el.get_text(strip=True)
            sezioni[current] += str(el)
        elif current:
            sezioni[current] += str(el)
    return (
        sezioni["Cosa è incluso"],
        sezioni["La quota viaggio non comprende"],
        sezioni["La quota della cassa comune comprende"],
        sezioni["Info aggiuntive"],
    )

# === MAIN ===
async def main():
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        template = Template(f.read())

    with open(INPUT_URLS_PATH, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]

    for url in urls:
        slug = slugify(url)
        local_html_path = f"input/{slug}.html"
        await estrai_html_con_playwright(url, local_html_path)

        with open(local_html_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')

        title = soup.title.string.strip() if soup.title else 'viaggio'
        output_filename = f'{slug}.html'
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        included, not_included, cassa_comune, extras = estrai_modale_formattata(soup)

        content = {
            'title': title,
            'heading': title,
            'summary': soup.find('div', class_='long-description').get_text(strip=True) if soup.find('div', class_='long-description') else 'Contenuto non trovato',
            'mood': estrai_blocco_per_titolo(soup, 'Mood di viaggio'),
            'physical_effort': estrai_blocco_per_titolo(soup, 'Impegno fisico'),
            'travel_requirements': estrai_blocco_per_titolo(soup, 'Cosa serve'),
            'meeting_info': estrai_blocco_per_titolo(soup, 'Ritrovo'),
            'day_by_day': estrai_itinerario(soup),
            'included': included,
            'not_included': not_included,
            'cassa_comune': cassa_comune,
            'extras': extras,
        }

        rendered_html = template.render(**content)
        with open(output_path, 'w', encoding='utf-8') as out:
            out.write(rendered_html)
        print(f"✅ Creato file: {output_path}")

        national_index_path = os.path.join(OUTPUT_DIR, 'index.html')
        national_link = f'<li><a href="{output_filename}">{title}</a></li>\n'
        if os.path.exists(national_index_path):
            with open(national_index_path, 'r', encoding='utf-8') as f:
                index_content = f.read()
            if national_link not in index_content:
                index_content = index_content.replace('</ul>', national_link + '</ul>')
        else:
            index_content = f"""<!DOCTYPE html>
<html lang=\"it\">
<head><meta charset=\"UTF-8\"><title>Viaggi in {ISO_CODE.upper()}</title></head>
<body>
<h1>Viaggi in {ISO_CODE.upper()}</h1>
<ul>{national_link}</ul>
</body></html>"""

        with open(national_index_path, 'w', encoding='utf-8') as f:
            f.write(index_content)
        print(f"📘 Index {ISO_CODE} aggiornato.")

        global_link = f'<li><a href="{ISO_CODE}/index.html">Viaggi in {ISO_CODE.upper()}</a></li>\n'
        if os.path.exists(GLOBAL_INDEX_PATH):
            with open(GLOBAL_INDEX_PATH, 'r', encoding='utf-8') as f:
                global_content = f.read()
            if global_link not in global_content:
                global_content = global_content.replace('</ul>', global_link + '</ul>')
        else:
            global_content = f"""<!DOCTYPE html>
<html lang=\"it\">
<head><meta charset=\"UTF-8\"><title>Index globale WeRoad</title></head>
<body>
<h1>Index globale - Viaggi per nazione</h1>
<ul>{global_link}</ul>
</body></html>"""

        with open(GLOBAL_INDEX_PATH, 'w', encoding='utf-8') as f:
            f.write(global_content)
        print("🌍 Index globale aggiornato.")

    try:
        subprocess.run(["git", "add", "docs/"], check=True)
        subprocess.run(["git", "commit", "-m", f"Aggiunti/aggiornati viaggi in {ISO_CODE.upper()}`"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("🚀 Modifiche pubblicate su GitHub!")
    except subprocess.CalledProcessError as e:
        print("⚠️ Errore durante i comandi Git:", e)

if __name__ == "__main__":
    asyncio.run(main())