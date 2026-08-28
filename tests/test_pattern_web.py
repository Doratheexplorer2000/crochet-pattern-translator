import base64
import io
import json
import subprocess
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from pattern_translator.api import app


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_browser_modules(script):
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


class PatternBrowserUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_ui_health_and_static_assets_are_served(self):
        response = self.client.get("/")
        self.assertEqual(200, response.status_code)
        self.assertIn("/static/app.js", response.text)
        self.assertEqual({"status": "ok"}, self.client.get("/health").json())
        for path in (
            "/static/styles.css",
            "/static/app.js",
            "/static/translations.js",
            "/static/crop_coordinates.js",
            "/static/workflow_state.js",
            "/static/fonts/SourceSansVF-Upright.ttf.BsWL4Kly.woff2",
            "/static/fonts/OFL.txt",
        ):
            self.assertEqual(200, self.client.get(path).status_code, path)

    def test_browser_config_contains_only_public_plausible_value(self):
        payload = self.client.get("/api/v1/browser-config").json()
        self.assertEqual({"plausible_script_url"}, set(payload))

    def test_language_placeholders_labels_and_canonical_form_values(self):
        payload = run_browser_modules(
            """
            import { readFileSync } from 'node:fs';
            const module = (path) => import('data:text/javascript,' + encodeURIComponent(readFileSync(path, 'utf8')));
            const { resolveUiLang, stringsFor, modeLabelFor } = await module('./pattern_translator/web/translations.js');
            const { canTranslate, translationFormEntries } = await module('./pattern_translator/web/workflow_state.js');
            const languages = ['en', 'zh-Hant', 'zh-Hans', 'ja'];
            const state = { file: { name: 'pattern.png' }, source: '', target: '', area: 'Whole Pattern', crop: null };
            console.log(JSON.stringify({
              resolved: [resolveUiLang('zh-Hant'), resolveUiLang('invalid', ['zh-CN']), resolveUiLang('', ['ja-JP']), resolveUiLang('', ['fr-FR'])],
              placeholders: languages.map((lang) => stringsFor(lang).chooseOption),
              labels: languages.map((lang) => modeLabelFor('English — US', lang)),
              initialCanTranslate: canTranslate(state),
              form: translationFormEntries({ ...state, source: 'English — US', target: 'Traditional Chinese', crop: [1, 2, 3, 4] }),
              validCanTranslate: canTranslate({ ...state, source: 'English — US', target: 'Traditional Chinese' }),
            }));
            """
        )
        self.assertEqual(["zh-Hant", "zh-Hans", "ja", "en"], payload["resolved"])
        self.assertEqual(["Choose an option", "請選擇", "请选择", "選択してください"], payload["placeholders"])
        self.assertEqual(["English — US", "美式英文", "英文 — 美式", "英語 — 米国式"], payload["labels"])
        self.assertFalse(payload["initialCanTranslate"])
        self.assertTrue(payload["validCanTranslate"])
        self.assertEqual(
            [["source_mode", "English — US"], ["output_mode", "Traditional Chinese"], ["area_mode", "Whole Pattern"],
             ["crop_left", "1"], ["crop_top", "2"], ["crop_right", "3"], ["crop_bottom", "4"]],
            payload["form"],
        )

    def test_request_and_image_generation_guards_prevent_stale_updates(self):
        payload = run_browser_modules(
            """
            import { readFileSync } from 'node:fs';
            const module = (path) => import('data:text/javascript,' + encodeURIComponent(readFileSync(path, 'utf8')));
            const { invalidateRequest, isCurrentImage, isCurrentRequest } = await module('./pattern_translator/web/workflow_state.js');
            const oldFile = { name: 'old.jpg' }, newFile = { name: 'new.jpg' };
            const state = { generation: 8, loading: true, controller: { abort() {} }, file: oldFile };
            const oldController = invalidateRequest(state);
            state.file = newFile;
            console.log(JSON.stringify({
              oldControllerPresent: Boolean(oldController),
              generation: state.generation,
              loading: state.loading,
              oldRequestCurrent: isCurrentRequest(state, 8),
              oldImageCurrent: isCurrentImage(state, 8, oldFile),
              newImageCurrent: isCurrentImage(state, 9, newFile),
            }));
            """
        )
        self.assertTrue(payload["oldControllerPresent"])
        self.assertEqual(9, payload["generation"])
        self.assertFalse(payload["loading"])
        self.assertFalse(payload["oldRequestCurrent"])
        self.assertFalse(payload["oldImageCurrent"])
        self.assertTrue(payload["newImageCurrent"])

    def test_error_adapter_never_returns_browser_or_parser_exception_text(self):
        payload = run_browser_modules(
            """
            import { readFileSync } from 'node:fs';
            const module = (path) => import('data:text/javascript,' + encodeURIComponent(readFileSync(path, 'utf8')));
            const { stringsFor } = await module('./pattern_translator/web/translations.js');
            const { adaptApiError } = await module('./pattern_translator/web/workflow_state.js');
            const text = stringsFor('en');
            console.log(JSON.stringify([
              adaptApiError(400, { detail: 'Invalid image' }, text),
              adaptApiError(422, { detail: [{ msg: 'proxy HTML' }] }, text),
              adaptApiError(500, { error: 'secret', request_id: 'safe-id' }, text),
              adaptApiError(503, null, text),
            ]));
            """
        )
        self.assertEqual(
            [
                "This file could not be read. Please choose another image.",
                "Please check the selected image and translation settings.",
                "Translation failed. Reference: safe-id",
                "Translation failed. Please try again.",
            ],
            payload,
        )

    def test_crop_coordinate_matrix_geometry_and_real_exif_jpegs(self):
        fixtures = {}
        for orientation in (2, 4, 5, 7):
            image = Image.new("RGB", (101, 59), "white")
            exif = Image.Exif()
            exif[274] = orientation
            output = io.BytesIO()
            image.save(output, format="JPEG", exif=exif)
            fixtures[str(orientation)] = base64.b64encode(output.getvalue()).decode("ascii")
        payload = run_browser_modules(
            f"""
            import {{ readFileSync }} from 'node:fs';
            const module = (path) => import('data:text/javascript,' + encodeURIComponent(readFileSync(path, 'utf8')));
            const {{ displayBoxToOriginal, normalizedCropBox, readExifOrientation, resizeCropBox }} = await module('./pattern_translator/web/crop_coordinates.js');
            const dimensions = {{ 1:[101,59], 2:[101,59], 3:[101,59], 4:[101,59], 5:[59,101], 6:[59,101], 7:[59,101], 8:[59,101] }};
            const full = Object.fromEntries(Object.entries(dimensions).map(([orientation, [width,height]]) => [orientation, displayBoxToOriginal({{left:0,top:0,right:width,bottom:height}}, Number(orientation), 101, 59)]));
            const boxes = {{
              1:[10,11,30,31], 2:[71,11,91,31], 3:[71,28,91,48], 4:[10,28,30,48],
              5:[11,10,31,30], 6:[28,10,48,30], 7:[28,71,48,91], 8:[11,71,31,91],
            }};
            const asymmetric = Object.fromEntries(Object.entries(boxes).map(([orientation, [left,top,right,bottom]]) => [orientation, displayBoxToOriginal({{left,top,right,bottom}}, Number(orientation), 101, 59)]));
            const fixtures = {json.dumps(fixtures)};
            console.log(JSON.stringify({{
              full, asymmetric,
              fractional: displayBoxToOriginal({{left:27.2,top:10.1,right:47.7,bottom:30.8}}, 6, 101, 59),
              clamped: displayBoxToOriginal({{left:-5,top:-2,right:110,bottom:70}}, 1, 101, 59),
              leftAnchored: resizeCropBox({{left:20,top:10,width:50,height:30}}, 'left', 100, 200, 100, 50),
              topAnchored: resizeCropBox({{left:20,top:10,width:30,height:50}}, 'top', 100, 200, 100, 50),
              normalised: normalizedCropBox({{left:-10,top:90,width:20,height:20}}, 100, 100, 50),
              exif: Object.fromEntries(Object.entries(fixtures).map(([orientation, encoded]) => [orientation, readExifOrientation(Uint8Array.from(atob(encoded), c => c.charCodeAt(0)).buffer)])),
            }}));
            """
        )
        expected_full = [0, 0, 101, 59]
        self.assertEqual({str(index): expected_full for index in range(1, 9)}, payload["full"])
        self.assertEqual({str(index): [10, 11, 30, 31] for index in range(1, 9)}, payload["asymmetric"])
        self.assertEqual([10, 11, 31, 32], payload["fractional"])
        self.assertEqual([0, 0, 101, 59], payload["clamped"])
        self.assertEqual({"left": 20, "top": 10, "width": 50, "height": 30}, payload["leftAnchored"])
        self.assertEqual({"left": 20, "top": 10, "width": 30, "height": 50}, payload["topAnchored"])
        self.assertEqual({"left": 0, "top": 50, "width": 50, "height": 50}, payload["normalised"])
        self.assertEqual({"2": 2, "4": 4, "5": 5, "7": 7}, payload["exif"])


if __name__ == "__main__":
    unittest.main()
