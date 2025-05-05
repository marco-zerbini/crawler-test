import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from jinja2 import Template
import os
import re

# === CONFIG ===
ISO_CODE = input("Inserisci il codice ISO-3 del paese (es. 'usa', 'jpn'): ").lower()
URL = input("Inserisci l'URL del viaggio WeRoad: ").strip()
OUTPUT_DIR = f'docs/{ISO_CODE}'
TEMPLATE_PATH = 'templates/template.html'
GLOBAL_INDEX_PATH = 'docs/index.html'
os.makedirs(OUTPUT_DIR, exist_ok=True)

async def estrai_contenuto_html(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.evaluate("document.documentElement.style.zoom = '0.7'")

        # Rimuove banner cookie se esiste
        try:
            await page.wait_for_selector('#iubenda-cs-banner', timeout=5000)
            await page.evaluate("document.getElementById('iubenda-cs-banner')?.remove()")
        except:
            pass

        # Espandi giorni itinerario
        accordion_icons = await page.locator('[data-testid="accordion-icon"]').all()
        for icon in accordion_icons:
            try:
                await icon.click()
                await page.wait_for_timeout(300)
            except:
                pass

        # Clic su bottone "Cassa comune"
        try:
            await page.evaluate("""
                [...document.querySelectorAll('div.flex')]
                    .find(el => el.innerText.includes('Cassa comune'))?.click();
            """)
            await page.wait_for_timeout(3000)
        except:
            pass

        html = await page.content()
        await browser.close()
        return html

def estrai_testo_blocco(soup, titolo):
    for h2 in soup.find_all('h2'):
        if titolo.lower() in h2.get_text(strip=True).lower():
            container = h2.find_parent()
            if container:
                return '\n'.join(p.get_text(strip=True) for p in container.find_all('p'))
    return 'Contenuto non trovato'

def estrai_blocco_html(soup, contenuto):
    for h2 in soup.find_all('h2'):
        if contenuto.lower() in h2.get_text(strip=True).lower():
            container = h2.find_parent()
            if container:
                return str(container)
    return '<p>Non trovato</p>'

async def main():
    html = await estrai_contenuto_html(URL)
    soup = BeautifulSoup(html, 'html.parser')

    title = soup.title.string.strip() if soup.title else 'viaggio'
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'\s+', '-', slug).strip('-')
    output_filename = f'{slug}.html'
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    content = {
        'title': title,
        'heading': title,
        'summary': soup.find('div', class_='long-description').get_text(strip=True) if soup.find('div', class_='long-description') else 'Contenuto non trovato',
        'mood': estrai_testo_blocco(soup, 'Mood di viaggio'),
        'physical_effort': estrai_testo_blocco(soup, 'Impegno fisico'),
        'travel_requirements': estrai_testo_blocco(soup, 'Cosa serve'),
        'meeting_info': estrai_testo_blocco(soup, 'Ritrovo'),
        'day_by_day': estrai_blocco_html(soup, 'Itinerario giorno per giorno'),
        'included': estrai_blocco_html(soup, 'Cosa è incluso'),
        'not_included': estrai_blocco_html(soup, 'non comprende'),
        'extras': estrai_blocco_html(soup, 'Info aggiuntive'),
    }

    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        template = Template(f.read())
    rendered_html = template.render(**content)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(rendered_html)
    print(f"✅ File generato: {output_path}")

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
<html lang=\"it\">
<head><meta charset=\"UTF-8\"><title>Viaggi in {ISO_CODE.upper()}</title></head>
<body><h1>Viaggi in {ISO_CODE.upper()}</h1><ul>{national_link}</ul></body></html>"""
    with open(national_index_path, 'w', encoding='utf-8') as f:
        f.write(index_content)

    # Aggiorna index globale
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
<body><h1>Index globale - Viaggi per nazione</h1><ul>{global_link}</ul></body></html>"""
    with open(GLOBAL_INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(global_content)

asyncio.run(main())
