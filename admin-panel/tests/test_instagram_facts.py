"""Instagram Facts editorial series tests: independent, bilingual, scheduled, no duplicates."""
import sys,unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch,AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from instagram_facts import FACTS,fact_caption,fact_key,next_fact,cycle_next_kind,feed_calendar, fact_media
from instagram_campaign import MSK
import instagram

FACT_LIST=[{"id":n,"title":"Факт "+str(n)} for n in range(1,16)]
CAMPAIGN={"enabled":True,"start_date":"2026-11-09","end_date":"2026-12-08"}
class FactsEditorialTests(unittest.TestCase):
 def test_all_15_bilingual_and_first_fact_always_first(self):
  self.assertEqual(len(FACTS),15)
  for f in FACT_LIST:
   caption=fact_caption(f)
   self.assertLess(caption.index("ART FACTS"),caption.index("ФАКТЫ ОБ ИСКУССТВЕ"))
   self.assertIn("#artfacts",caption)
   self.assertIn("#фактыобискусстве",caption)
   self.assertLess(len(caption),2200)
  state={"records":{},"used_indices":[0,1,2,3],"used_ids":["anything"]}
  self.assertEqual(next_fact(FACT_LIST,state)["id"],1)
  self.assertEqual(cycle_next_kind(state),"fact")
  self.assertEqual(fact_media(FACT_LIST[0]).split("/")[-1],"fact-01.jpg")

 def test_independent_cycle_fact_painting_painting(self):
  state={"records":{}}
  self.assertEqual(cycle_next_kind(state),"fact")
  state["records"]["igfact:1"]={"editorial_cycle":True,"status":"accepted","created_at":"2026-11-12T00:00:00Z"}
  self.assertEqual(cycle_next_kind(state),"artwork")
  state["records"]["p1"]={"editorial_cycle":True,"status":"sent","created_at":"2026-11-13T00:00:00Z"}
  self.assertEqual(cycle_next_kind(state),"artwork")
  state["records"]["p2"]={"editorial_cycle":True,"status":"accepted","created_at":"2026-11-14T00:00:00Z"}
  self.assertEqual(cycle_next_kind(state),"fact")
  self.assertEqual(next_fact(FACT_LIST,state)["id"],2)

 def test_calendar_first_is_fact_and_moscow_time(self):
  state={"campaign":CAMPAIGN,"records":{},"ig_facts_enabled":True}
  plan=feed_calendar(state,FACT_LIST,now=datetime(2026,11,12,12,0,tzinfo=MSK),count=4)
  self.assertEqual([x["kind"] for x in plan],["fact","artwork","artwork","fact"])
  self.assertEqual(plan[0]["id"],"1")
  self.assertEqual(plan[3]["id"],"2")
  self.assertTrue(all(x["at"].endswith("+03:00") for x in plan))

 def test_calendar_predicts_actual_artworks_and_media_types(self):
  from instagram_facts import artwork_key
  artworks=[
   {"title":"Кафе в Венеции","artist":"Владимир Кожевников","photo":"https://example.com/1.jpg",
    "link":"https://ivory-art.com/#ia-product-216435722902"},
   {"title":"Жаркое лето","artist":"Алексей Рычков","photo":"https://example.com/2.jpg",
    "link":"https://ivory-art.com/#ia-product-477049108772"}]
  media={artwork_key(p):{"images":["one.jpg","two.jpg"],"reel":"video.mp4",
                         "reel_style":"luxury"} for p in artworks}
  state={"campaign":CAMPAIGN,"records":{"older":{"campaign":True,"kind":"artwork",
           "status":"sent","format":"reel","campaign_date":"2026-11-09"}},
         "ig_facts_enabled":True,"rich_media_enabled":True}
  plan=feed_calendar(state,FACT_LIST,now=datetime(2026,11,12,12,0,tzinfo=MSK),
                     artworks=artworks,media=media,count=3)
  self.assertEqual(plan[0]["kind"],"fact")
  self.assertEqual(plan[1]["title"],"Кафе в Венеции")
  self.assertEqual(plan[1]["format"],"carousel")
  self.assertEqual(plan[2]["title"],"Жаркое лето")
  self.assertEqual(plan[2]["format"],"reel")
  self.assertEqual(plan[2]["id"],artwork_key(artworks[1]))

 def test_editorial_caption_override_used_by_buffer(self):
  import asyncio
  async def check():
   post={"photo":"https://example.com/a.jpg","instagram_caption":"Fact first in English.\nФакт по-русски.\n#artfacts #фактыобискусстве"}
   with patch.object(instagram,"graphql",new=AsyncMock(return_value={"createPost":{"post":{"id":"remote","status":"sending"}}})) as call:
    result=await instagram.create_buffer_post("channel",post,post["photo"])
    self.assertEqual(result["id"],"remote")
    self.assertEqual(call.call_args.args[1]["input"]["text"],post["instagram_caption"])
  asyncio.run(check())

if __name__=="__main__":unittest.main()
