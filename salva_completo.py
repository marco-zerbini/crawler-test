import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import os

async def salva_pagina_completa(url: str, output_path: str):
    print(f"🌐 Caricamento pagina: {url}")
    os.makedirs("output", exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=200)
        page = await browser.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # 👇 Applica zoom 70%
            await page.evaluate("document.documentElement.style.zoom = '0.7'")
            print("🔍 Zoom impostato al 70%")
        except Exception as e:
            print(f"❌ Timeout o errore durante il caricamento: {e}")
            await browser.close()
            return

        # 1️⃣ Rimuovi cookie banner
        try:
            await page.wait_for_selector('#iubenda-cs-banner', timeout=10000)
            await page.evaluate("""() => {
                const el = document.getElementById('iubenda-cs-banner');
                if (el) el.remove();
            }""")
            print("🍪 Banner Iubenda rimosso.")
        except:
            print("ℹ️ Nessun banner Iubenda trovato.")

        # 2️⃣ Espandi accordion itinerario
        try:
            accordion_icons = await page.locator('[data-testid="accordion-icon"]').all()
            for icon in accordion_icons:
                try:
                    await icon.click()
                    await page.wait_for_timeout(500)
                except:
                    pass
            print(f"📅 {len(accordion_icons)} giorni espansi.")
        except:
            print("⚠️ Nessun accordion trovato.")

        # 3️⃣ Click su "Cassa comune?" e attesa contenuto modale
        try:
            await page.wait_for_timeout(3000)
            print("🧪 Click su 'Cassa comune?' con el.click()...")

            await page.evaluate("""
                () => {
                    const el = [...document.querySelectorAll('div.flex')]
                        .find(el => el.innerText.includes('Cassa comune'));
                    if (el) el.click();
                }
            """)
            await page.wait_for_timeout(3000)

            await page.wait_for_selector("h2:text('Info aggiuntive')", timeout=7000)
            print("✅ Modale aperta e contenuto 'Info aggiuntive' trovato.")

            modal_text = await page.evaluate("""
                () => {
                    const modal = document.querySelector('.wr-modal-external-container');
                    return modal ? modal.innerText : null;
                }
            """)
            if modal_text:
                with open("output/cassa_comune.txt", "w", encoding="utf-8") as f:
                    f.write(modal_text)
                print("📝 Contenuto modale salvato in output/cassa_comune.txt")
            else:
                print("❌ Testo modale vuoto anche dopo attesa.")
        except Exception as e:
            print("❌ Errore durante apertura modale o attesa contenuto:", e)
            await page.screenshot(path="output/error_modal_click.png", full_page=True)

        await page.screenshot(path="output/finale.png", full_page=True)
        print("📸 Screenshot finale salvato.")

        # 4️⃣ Salva HTML originale completo
        html = await page.content()
        with open("output/raw_dom_dump.html", "w", encoding="utf-8") as f:
            f.write(html)

        # 5️⃣ Pulizia e salvataggio HTML statico
        soup = BeautifulSoup(html, 'html.parser')
        for style in soup.find_all('style'):
            style.decompose()
        for link in soup.find_all('link', rel='stylesheet'):
            link.decompose()

        selettori_da_rimuovere = [
            'header', 'footer', 'nav', 'script', 'style', 'noscript', 'svg', 'head',
            '#iubenda-cs-banner',
            '[data-testid="trustpilot-wrapper"]',
            '[class*="Navbar"]',
            'div[data-testid="floating-buttons"]',
            '[role="alert"]',
            '[role="banner"]',
            '[role="alertdialog"]',
            '[role="region"][aria-label*="skip" i]'
        ]
        for selector in selettori_da_rimuovere:
            for el in soup.select(selector):
                el.decompose()

        for dialog in soup.find_all('div', {'role': 'dialog'}):
            if dialog.get('aria-modal') != 'true':
                dialog.decompose()

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(str(soup))

        print("🧹 HTML ripulito e salvato.")
        print(f"✅ File finale: {output_path}")

# === ESEMPIO USO ===
if __name__ == "__main__":
    url = "https://www.weroad.it/viaggi/giappone"
    output = "output/giappone360_completo.html"
    asyncio.run(salva_pagina_completa(url, output))
