import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={'width':1200,'height':900}, color_scheme='light')
        errs=[]; pg.on('pageerror', lambda e: errs.append(str(e))); pg.on('console', lambda m: errs.append(m.text) if m.type=='error' else None)
        await pg.goto('file://' + sys.argv[1] + (sys.argv[3] if len(sys.argv)>3 else '')); await pg.wait_for_timeout(1500)
        await pg.screenshot(path=sys.argv[2], full_page=True)
        kp = await pg.eval_on_selector_all('.kpi', 'els=>els.map(e=>e.querySelector(".l").textContent+": "+e.querySelector(".v").textContent)')
        print('\n'.join(kp)); print('subtitle:', await pg.text_content('#subtitle')); print('errors:', errs)
        await b.close()
asyncio.run(main())
