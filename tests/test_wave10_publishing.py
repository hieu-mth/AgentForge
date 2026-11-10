"""Wave 10 local release, OAuth private-only and Owner HTTP contracts.

Mock source MP4 and Google SDK are fixtures; tests do NOT certify a channel,
a public posting, monetization, bank reconciliation or platform statistics.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from agentforge.features.film_studio import production, publishing
from agentforge.integrations import youtube_private
from tests.test_wave9_film_production import FilmProductionWave9Tests

METADATA = {
    "title": "Original Forest Documentary",
    "description": "Original cinematic film made with Owner-reviewed media.",
    "synthetic_media": True, "made_for_kids": False,
    "rights_attested": True, "owner_watched": True,
    "planned_utc": None, "campaign": None,
}
VIDEO_ID = "AbCdef123_-"


class FilmPublishingWave10Tests(unittest.TestCase):
    def setUp(self):
        w9 = FilmProductionWave9Tests("test_owner_gated_ffmpeg_render_and_receipt")
        w9.setUp()
        self.addCleanup(w9.doCleanups)
        self.w9 = w9
        self.folder = w9._render_mock()
        self.films = w9.films
        self.db = w9.root / "data" / "release.sqlite3"
        self.source = production.inspect("episode-one", "fox-film", film_root=self.films)
        self.render = production.inspect_render("episode-one", "fox-film", film_root=self.films)

    def _prepare(self, *, metadata=METADATA, confirmed=True):
        return publishing.prepare(
            film_slug="fox-film", episode_id="episode-one",
            episode_sha=self.source["episode_sha256"],
            render_sha=self.render["receipt_sha256"],
            metadata=metadata, confirmed=confirmed,
            db_path=self.db, film_root=self.films)

    def _inspect(self, release_id):
        return publishing.inspect(release_id, db_path=self.db, film_root=self.films)

    def test_prepare_is_local_immutable_sha_reviewed_rights_required(self):
        with self.assertRaises(PermissionError):
            self._prepare(confirmed=False)
        with self.assertRaises(PermissionError):
            self._prepare(metadata={**METADATA, "rights_attested": False})
        with self.assertRaises(PermissionError):
            self._prepare(metadata={**METADATA, "owner_watched": False})
        with self.assertRaises(PermissionError):
            publishing.prepare(
                film_slug="fox-film",episode_id="episode-one",
                episode_sha=self.source["episode_sha256"],
                render_sha="0"*64,metadata=METADATA,confirmed=True,
                db_path=self.db,film_root=self.films)
        self.assertFalse(self.db.exists())
        result = self._prepare()
        self.assertEqual(result["status"], "READY_FOR_MANUAL_HANDOFF")
        self.assertEqual(result["video_sha256"], self.render["video_sha256"])
        self.assertEqual(result["initial_privacy"], "private")
        self.assertFalse(result["auto_publication"])
        self.assertFalse(result["public_approval_given"])
        self.assertFalse(result["platform_api_connected"])
        self.assertFalse(result["revenue_verified"])
        with self.assertRaises(FileExistsError):
            self._prepare()
        listed=publishing.summary(db_path=self.db,film_root=self.films)
        self.assertEqual(len(listed["releases"]),1)
        self.assertFalse(listed["auto_publish"])
        self.assertIsNone(listed["verified_net_profit_vnd"])
        handed=publishing.handoff(result["release_id"], db_path=self.db,film_root=self.films)
        self.assertEqual(handed["metadata"]["privacy"], "private")
        self.assertTrue(handed["video_file"].endswith("episode.mp4"))

    def test_plan_date_is_timezone_aware_future_only_and_not_actual_schedule(self):
        soon=(datetime.now(timezone.utc)+timedelta(seconds=2)).isoformat()
        with self.assertRaises(publishing.PublishingError):
            self._prepare(metadata={**METADATA,"planned_utc":soon})
        with self.assertRaises(publishing.PublishingError):
            self._prepare(metadata={**METADATA,"planned_utc":"2026-12-01T08:00:00"})
        tomorrow=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
        result=self._prepare(metadata={**METADATA,"planned_utc":tomorrow})
        self.assertEqual(result["planned_utc"],tomorrow)
        self.assertFalse(result["platform_posting_scheduled"])

    def test_private_upload_is_one_shot_no_retry_and_owner_attest_never_verified(self):
        item=self._prepare()
        rid,sha=item["release_id"],item["release_sha256"]
        with self.assertRaises(PermissionError):
            publishing.checkpoint_private_upload(rid,sha,db_path=self.db,film_root=self.films)
        publishing.checkpoint_private_upload(
            rid,sha,confirmed=True,db_path=self.db,film_root=self.films)
        self.assertEqual(self._inspect(rid)["status"],"UPLOAD_ATTEMPT_UNCERTAIN")
        with self.assertRaises(PermissionError):
            publishing.checkpoint_private_upload(
                rid,sha,confirmed=True,db_path=self.db,film_root=self.films)
        publishing.complete_private_upload(rid,sha,VIDEO_ID,db_path=self.db)
        self.assertEqual(self._inspect(rid)["status"],"PRIVATE_UPLOADED_API")
        with self.assertRaises(PermissionError):
            publishing.complete_private_upload(rid,sha,VIDEO_ID,db_path=self.db)
        with self.assertRaises(PermissionError):
            publishing.owner_attest(rid,"f"*64,VIDEO_ID,"public",
                                    confirmed=True,db_path=self.db,film_root=self.films)
        with self.assertRaises(PermissionError):
            publishing.owner_attest(rid,sha,"ZZZdef123_-","public",
                                    confirmed=True,db_path=self.db,film_root=self.films)
        claimed=publishing.owner_attest(rid,sha,VIDEO_ID,"public",
            confirmed=True,db_path=self.db,film_root=self.films)
        self.assertEqual(claimed["status"],"OWNER_REPORTED_PUBLIC")
        self.assertFalse(claimed["platform_publication_verified"])
        self.assertFalse(claimed["public_approval_given"])
        self.assertFalse(claimed["revenue_verified"])

    def test_platform_owner_observation_not_fake_api_analytics(self):
        item=self._prepare()
        rid,sha=item["release_id"],item["release_sha256"]
        snapshot={"date":datetime.now(timezone.utc).date().isoformat(),
                  "views":120,"likes":10,"comments":2,"watch_minutes":80}
        with self.assertRaises(publishing.PublishingError):
            publishing.observe(rid,sha,snapshot,confirmed=True,
                               db_path=self.db,film_root=self.films)
        publishing.owner_attest(rid,sha,VIDEO_ID,"private",
                                confirmed=True,db_path=self.db,film_root=self.films)
        with self.assertRaises(PermissionError):
            publishing.observe(rid,sha,snapshot,db_path=self.db,film_root=self.films)
        result=publishing.observe(rid,sha,snapshot,confirmed=True,
                                  db_path=self.db,film_root=self.films)
        self.assertTrue(result["owner_reported"])
        self.assertFalse(result["platform_api_verified"])
        with self.assertRaises(publishing.PublishingError):
            publishing.observe(rid,sha,snapshot,confirmed=True,
                                db_path=self.db,film_root=self.films)
        with self.assertRaises(publishing.PublishingError):
            publishing.observe(rid,sha,{**snapshot,"views":-2,
                "date":"2025-01-01"},confirmed=True,db_path=self.db,film_root=self.films)
        self.assertEqual(publishing.summary(db_path=self.db,film_root=self.films)[
            "releases"][0]["latest_observation"]["views"],120)

    def test_tampered_final_mp4_prevents_upload_or_release_inspection(self):
        item=self._prepare()
        self.folder.joinpath("episode.mp4").write_bytes(b"tampered")
        with self.assertRaises(production.FilmProductionError):
            self._inspect(item["release_id"])
        with self.assertRaises(production.FilmProductionError):
            publishing.checkpoint_private_upload(
                item["release_id"],item["release_sha256"],confirmed=True,
                db_path=self.db,film_root=self.films)
        # Ledger is read-only except on an explicitly authorized action.
        self.assertEqual(publishing.list_releases(
            db_path=self.db,film_root=self.films)[0]["status"],
            "INTEGRITY_REVIEW_REQUIRED")

    def test_optional_oauth_private_only_transport_mock(self):
        item=self._prepare()
        rid,sha=item["release_id"],item["release_sha256"]
        with tempfile.TemporaryDirectory() as tmp:
            client=Path(tmp)/"desktop-client.json"
            client.write_text('{"installed":{}}',encoding="utf-8")
            with patch.object(youtube_private.ops_control,"require_active"),\
                 patch.object(youtube_private,"_authorize",return_value=object()) as auth,\
                 patch.object(youtube_private,"_dispatch",return_value=VIDEO_ID) as transport:
                result=youtube_private.upload_private(
                    rid,sha,client_secrets_path=client,confirmed=True,
                    db_path=self.db,film_root=self.films)
            auth.assert_called_once()
            self.assertEqual(transport.call_count,1)
            self.assertEqual(transport.call_args.args[2]["initial_privacy"],"private")
            self.assertEqual(result["status"],"PRIVATE_UPLOADED_API")
            self.assertFalse(result["credentials_saved"])
            with patch.object(youtube_private,"_dispatch") as again,\
                 patch.object(youtube_private.ops_control,"require_active"):
                with self.assertRaises(PermissionError):
                    youtube_private.upload_private(
                        rid,sha,client_secrets_path=client,confirmed=True,
                        db_path=self.db,film_root=self.films)
                again.assert_not_called()

    def test_ambiguous_youtube_api_exception_blocks_duplicate_attempt(self):
        item=self._prepare()
        rid,sha=item["release_id"],item["release_sha256"]
        with tempfile.TemporaryDirectory() as tmp:
            client=Path(tmp)/"desktop-client.json"
            client.write_text('{"installed":{}}')
            with patch.object(youtube_private.ops_control,"require_active"),\
                 patch.object(youtube_private,"_authorize",return_value=object()),\
                 patch.object(youtube_private,"_dispatch",side_effect=TimeoutError("secret")):
                with self.assertRaisesRegex(RuntimeError,"YOUTUBE_UPLOAD_UNCERTAIN") as caught:
                    youtube_private.upload_private(
                        rid,sha,client_secrets_path=client,confirmed=True,
                        db_path=self.db,film_root=self.films)
            self.assertNotIn("secret",str(caught.exception))
            self.assertEqual(self._inspect(rid)["status"],"UPLOAD_ATTEMPT_UNCERTAIN")

    def test_sdk_client_build_cannot_request_public_or_schedule(self):
        import sys
        from unittest.mock import MagicMock
        service=MagicMock()
        request=MagicMock()
        request.next_chunk.return_value=(None,{"id":VIDEO_ID,
                                               "status":{"privacyStatus":"private"}})
        service.videos.return_value.insert.return_value=request
        discovery=SimpleNamespace(build=lambda *a,**kw:service)
        media=SimpleNamespace(MediaFileUpload=lambda *a,**kw:"MEDIA")
        with patch.dict(sys.modules,{
            "googleapiclient":SimpleNamespace(),
            "googleapiclient.discovery":discovery,
            "googleapiclient.http":media,
        }):
            item=self._prepare()
            returned=youtube_private._dispatch("fake.mp4",object(),item)
        self.assertEqual(returned,VIDEO_ID)
        args=service.videos.return_value.insert.call_args.kwargs
        self.assertEqual(args["body"]["status"]["privacyStatus"],"private")
        self.assertNotIn("publishAt",args["body"]["status"])
        self.assertTrue(args["body"]["status"]["containsSyntheticMedia"])
        self.assertTrue(args["body"]["status"]["selfDeclaredMadeForKids"] is False)


class Wave10PublishingHttpTests(unittest.TestCase):
    def setUp(self):
        from tests.test_webapp_revision_http_v41 import WebappRevisionHttpTests
        fixture=WebappRevisionHttpTests(
            "test_get_requires_login_and_allows_signed_source_review")
        fixture.setUp();self.addCleanup(fixture.doCleanups);self.http=fixture
        self.slug="fox-film";self.episode="episode-one"
        self.sha="a"*64;self.render_sha="b"*64
        self.rid="c"*32;self.release_sha="d"*64
        self.release={
            "release_id":self.rid,"release_sha256":self.release_sha,
            "film_slug":self.slug,"episode_id":self.episode,
            "status":"READY_FOR_MANUAL_HANDOFF", "video_sha256":"e"*64,
            "youtube_video_id":None,"title":"Owner release",
        }

    def test_authenticated_reviewed_sha_and_csrf_are_required(self):
        from agentforge.features.film_studio import production
        detail="/api/film/productions/"+self.slug+"/"+self.episode
        preview="/api/publishing/"+self.rid
        payload={"ack":"PREPARE_PRIVATE_RELEASE","film_slug":self.slug,
                 "episode_id":self.episode,"episode_sha":self.sha,
                 "render_sha":self.render_sha,"metadata":METADATA}
        with patch.object(production,"inspect",return_value={
                "episode_sha256":self.sha,"film_slug":self.slug,"episode_id":self.episode}),\
             patch.object(production,"_folder",return_value=Path(self.http.brain).parent/"none"),\
             patch.object(publishing,"prepare",return_value=self.release) as maker,\
             patch.object(publishing,"inspect",return_value=self.release) as viewer:
            self.assertEqual(self.http.req("GET","/api/publishing")[0],401)
            self.http.login()
            self.assertEqual(self.http.req("POST","/api/publishing/prepare",payload)[0],400)
            self.assertEqual(self.http.req("GET",detail)[0],200)
            self.assertEqual(self.http.req("POST","/api/publishing/prepare",
                                          payload,csrf=False)[0],403)
            self.assertEqual(self.http.req("POST","/api/publishing/prepare",
                {**payload,"episode_sha":"0"*64})[0],400)
            self.assertEqual(self.http.req("POST","/api/publishing/prepare",payload)[0],200)
            maker.assert_called_once()
            attest={"ack":"ATTEST_YOUTUBE_STUDIO_STATE","release_sha":self.release_sha,
                    "video_id":VIDEO_ID,"privacy":"private","owner_changed_on_youtube":True}
            with patch.object(publishing,"owner_attest",return_value=self.release) as recorder:
                self.assertEqual(self.http.req("POST",preview+"/attest",attest)[0],400)
                self.assertEqual(self.http.req("GET",preview)[0],200)
                self.assertEqual(self.http.req("POST",preview+"/attest",
                    {**attest,"release_sha":"0"*64})[0],400)
                self.assertEqual(self.http.req("POST",preview+"/attest",attest)[0],200)
                recorder.assert_called_once()
            viewer.assert_called()


if __name__=="__main__":
    unittest.main()
