"""No-network checks for the three-part Instagram Story publisher."""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import instagram


BASE="https://raw.githubusercontent.com/DmiriiX/ivory-bot/main/instagram-media/prepared/"
ARTWORK="artwork-1"

class HeadResponse:
    status_code=200
    headers={"content-type":"image/jpeg"}

class FakeClient:
    async def __aenter__(self): return self
    async def __aexit__(self,*exc): return False
    async def head(self,url): return HeadResponse()

class StoryTriptychTests(unittest.TestCase):
    def mock_backend(self):
        state={"enabled":True,"campaign":{"enabled":True},
               "story_records":{},
               "records":{ARTWORK:{"status":"sent","created_at":"2026-11-09T12:00:00Z"}}}
        images={"artworks":{ARTWORK:{"stories":[BASE+f"{ARTWORK}-story-{n}.jpg" for n in range(1,4)]}}}
        posts=[{"title":"Test Artwork","photo":"https://static.tildacdn.com/valid.jpg",
                "artist":"Artist", "link":"https://ivory-art.com/#ia-product-123456789000"}]
        async def read_file(kind,path):
            return {"instagram_state.json":state,"posts.json":posts,"instagram_assets.json":images}[path], "sha123"
        async def update_file(kind,path,data,sha,message):
            return {"content":{"sha":"sha123"}}
        return state,read_file,update_file

    def test_three_stories_accepted_and_repeat_is_idempotent(self):
        state,read_file,update_file=self.mock_backend()
        sender=AsyncMock(side_effect=[{"id":"buffer1","status":"sending"},
                                       {"id":"buffer2","status":"sending"},
                                       {"id":"buffer3","status":"sending"}])
        async def run():
            with patch.object(instagram,"due_now",return_value=True), \
                 patch.object(instagram,"instagram_channel",new=AsyncMock(return_value={"id":"ch"})), \
                 patch.object(instagram,"create_buffer_post",new=sender), \
                 patch.object(instagram,"get_buffer_status",new=AsyncMock(return_value={"status":"sending"})), \
                 patch.object(instagram.httpx,"AsyncClient",return_value=FakeClient()):
                first=await instagram.sync_instagram_story(
                    read_file,update_file,lambda kind,post:ARTWORK)
                second=await instagram.sync_instagram_story(
                    read_file,update_file,lambda kind,post:ARTWORK)
            return first,second
        first,second=asyncio.run(run())
        self.assertTrue(first["ok"])
        self.assertEqual(first["slides_accepted"],3)
        self.assertEqual(second["slides_accepted"],3)
        self.assertEqual(sender.await_count,3)
        self.assertEqual(len(state["story_records"]),3)
        self.assertEqual({v["slide"] for v in state["story_records"].values()}, {1,2,3})
        self.assertTrue(all(v["status"]=="accepted" for v in state["story_records"].values()))

    def test_failed_middle_slide_cannot_be_retried_or_duplicated(self):
        state,read_file,update_file=self.mock_backend()
        sender=AsyncMock(side_effect=[{"id":"buffer1","status":"sending"},
                                      ValueError("Rejected slide")])
        async def run():
            with patch.object(instagram,"due_now",return_value=True), \
                 patch.object(instagram,"instagram_channel",new=AsyncMock(return_value={"id":"ch"})), \
                 patch.object(instagram,"create_buffer_post",new=sender), \
                 patch.object(instagram,"get_buffer_status",new=AsyncMock(return_value={"status":"sending"})), \
                 patch.object(instagram.httpx,"AsyncClient",return_value=FakeClient()):
                first=await instagram.sync_instagram_story(
                    read_file,update_file,lambda kind,post:ARTWORK)
                second=await instagram.sync_instagram_story(
                    read_file,update_file,lambda kind,post:ARTWORK)
            return first,second
        first,second=asyncio.run(run())
        self.assertFalse(first["ok"])
        self.assertFalse(second["ok"])
        self.assertEqual(sender.await_count,2)
        self.assertEqual(len(state["story_records"]),2)


if __name__=="__main__":
    unittest.main()
