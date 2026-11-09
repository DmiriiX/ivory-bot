"""Diagnostic: print only public Tilda store configuration markers, no secrets."""
import asyncio
import re
import httpx

async def main():
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        for page in ("https://ivory-art.com/catalog", "https://ivory-art.com/"):
            try:
                r = await client.get(page, headers={"User-Agent":"Mozilla/5.0"})
                s = r.text
                print("PAGE",r.status_code,"bytes",len(r.content))
                for pattern in (r"storepartuid.{0,100}", r"t-store[^\n]{0,80}", r"rec\d{9,12}", r"getproductslist.{0,150}"):
                    matches=list(dict.fromkeys(re.findall(pattern,s,re.I)))
                    print(pattern[:20],"matches",len(matches),"examples",matches[:5])
            except Exception as exc:
                print("Fetch failure",type(exc).__name__)
asyncio.run(main())
