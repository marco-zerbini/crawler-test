import asyncio
import os
import re
from pathlib import Path
from bs4 import BeautifulSoup
from jinja2 import Template
from playwright.async_api import async_playwright
import subprocess

# === CONFIG ===
ISO_CODE = input("Inserisci il codice ISO-3 del paese (es. 'usa', 'jpn'): ").lower()
INPUT_URLS_PATH = 'input/urls.txt'
TEMPLATE_PATH = 'templates/template.html'
OUTPUT_DIR = f'docs/{ISO_CODE}'
GLOBAL_INDEX_PATH = 'docs/index.html'

os.makedirs(OUTPUT_DIR, exist_ok=True)

# === UTIL ===
def slugify(text):
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"\s+", "-", slug).strip("-")
    return slug

# === PLAYWRIGHT: ESTRAI HTML, MODALE, ITINERARIO ===
async def estrai_html_modale_e_itinerario(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=200)
        page = await browser.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.evaluate("document.documentElement.style.zoom = '0.7'")
        except Exception as e:
            print(f"❌ Errore caricamento {url}: {e}")
            return None, None, None

        try:
            await page.locator("button", has_text="Accetta tutti").click(timeout=5000)
            await page.wait_for_timeout(1000)
        except:
            pass

        await page.evaluate("""() => {
            document.querySelectorAll('[data-name="accordion-toggler"]').forEach(el => el.click());
        }""")
        for y in range(0, 5000, 300):
            await page.evaluate(f"window.scrollTo(0, {y})")
            await page.wait_for_timeout(200)

        await page.wait_for_timeout(1000)

        titoli = await page.eval_on_selector_all(
            "div[data-name='accordion-header'] h4",
            "els => els.map(el => el.innerText.trim())"
        )

        raw_blocchi = await page.query_selector_all("div[data-name='substage']")
        descrizioni_per_giorno = []
        for blocco in raw_blocchi:
            paragrafi = await blocco.query_selector_all("div.description.content p")
            testi = []
            for p in paragrafi:
                txt = (await p.inner_text()).strip()
                if txt:
                    testi.append(txt)
            descrizioni_per_giorno.append(testi)

        blocchi = []
        for i, titolo in enumerate(titoli):
            paragrafi = descrizioni_per_giorno[i] if i < len(descrizioni_per_giorno) else []
            blocco_html = f"<section class='giorno'>\n<h3>Giorno {i+1}: {titolo}</h3>\n"
            for p in paragrafi:
                blocco_html += f"<p>{p}</p>\n"
            blocco_html += "</section>\n"
            blocchi.append(blocco_html)

        # Click su "Cassa comune"
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

        modal_text = await page.evaluate("""
            () => {
                const modal = document.querySelector('.wr-modal-external-container');
                return modal ? modal.innerText : null;
            }
        """)

        title = await page.title()
        html = await page.content()
        await browser.close()

        return title, "\n".join(blocchi), modal_text, html

# === PARSING MODALE ===
def parse_modale_txt(modal_text):
    sezioni = {
        "Cosa è incluso": "",
        "La quota viaggio non comprende": "",
        "La quota della cassa comune comprende": "",
        "Info aggiuntive": ""
    }
    current = None
    for line in modal_text.splitlines():
        line = line.strip()
        if line in sezioni:
            current = line
            continue
        if current and line:
            sezioni[current] += f"<p>{line}</p>\n"
    return (
        sezioni["Cosa è incluso"],
        sezioni["La quota viaggio non comprende"],
        sezioni["La quota della cassa comune comprende"],
        sezioni["Info aggiuntive"]
    )

# === MAIN ===
async def main():
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        template = Template(f.read())

    with open(INPUT_URLS_PATH, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]

    for url in urls:
        title, day_by_day, modal_txt, html = await estrai_html_modale_e_itinerario(url)
        if not title:
            continue

        soup = BeautifulSoup(html, 'html.parser')
        included, not_included, cassa_comune, extras = parse_modale_txt(modal_txt or "")

        summary = soup.find('div', class_='long-description')
        summary_text = summary.get_text(strip=True) if summary else 'Contenuto non trovato'

        def estrai_blocco_per_titolo(soup, titolo):
            blocchi = soup.find_all('h2')
            for h2 in blocchi:
                if titolo.lower() in h2.get_text(strip=True).lower():
                    container = h2.find_parent()
                    if container:
                        testo = '\n'.join(p.get_text(strip=True) for p in container.find_all('p'))
                        return testo
            return 'Contenuto non trovato'

        content = {
            'title': title,
            'heading': title,
            'summary': summary_text,
            'mood': estrai_blocco_per_titolo(soup, 'Mood di viaggio'),
            'physical_effort': estrai_blocco_per_titolo(soup, 'Impegno fisico'),
            'travel_requirements': estrai_blocco_per_titolo(soup, 'Cosa serve'),
            'meeting_info': estrai_blocco_per_titolo(soup, 'Ritrovo'),
            'day_by_day': day_by_day,
            'included': included,
            'not_included': not_included,
            'cassa_comune': cassa_comune,
            'extras': extras,
        }

        slug = slugify(title)
        output_filename = f'{slug}.html'
        output_path = os.path.join(OUTPUT_DIR, output_filename)
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
<html lang=\"it\">
<head><meta charset=\"UTF-8\"><title>Viaggi in {ISO_CODE.upper()}</title></head>
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
<html lang=\"it\">
<head><meta charset=\"UTF-8\"><title>Index globale WeRoad</title></head>
<body>
<h1>Index globale - Viaggi per nazione</h1>
<ul>{global_link}</ul>
</body></html>"""

        with open(GLOBAL_INDEX_PATH, 'w', encoding='utf-8') as f:
            f.write(global_content)
        print("🌍 Index globale aggiornato.")

        # Git push opzionale
        try:
            subprocess.run(["git", "add", "docs/"], check=True)
            subprocess.run(["git", "commit", "-m", f"Aggiunto/aggiornato viaggio {title}"], check=True)
            subprocess.run(["git", "push"], check=True)
            print("🚀 Modifiche pubblicate su GitHub!")
        except subprocess.CalledProcessError as e:
            print("⚠️ Errore durante il push Git:", e)

if __name__ == "__main__":
    asyncio.run(main())
