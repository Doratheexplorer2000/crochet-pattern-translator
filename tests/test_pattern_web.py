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
            const file = { name: 'pattern.png' };
            const state = {
              file, source: '', target: '', area: 'Whole Pattern', crop: null,
              qualityAssessment: { level: 'good' }, qualityFile: file,
              qualityArea: 'Whole Pattern', qualityCrop: null,
              qualityConfirmed: false, qualityLoading: false,
            };
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
             ["crop_left", "1"], ["crop_top", "2"], ["crop_right", "3"], ["crop_bottom", "4"], ["force_run", "false"]],
            payload["form"],
        )

    def test_real_file_and_formdata_png_mime_variants_remain_compatible(self):
        payload = run_browser_modules(
            """
            import { readFileSync } from 'node:fs';
            const module = (path) => import('data:text/javascript,' + encodeURIComponent(readFileSync(path, 'utf8')));
            const { validateImageFile } = await module('./pattern_translator/web/workflow_state.js');
            const maxBytes = 25 * 1024 * 1024;
            const files = {
              emptyMime: new File(['png'], 'pattern.PNG', { type: '' }),
              legacyPng: new File(['png'], 'pattern.png', { type: 'image/x-png' }),
              binaryPng: new File(['png'], 'pattern.png', { type: 'application/octet-stream' }),
              canonicalPng: new File(['png'], 'pattern.png', { type: 'image/png' }),
              wrongMime: new File(['png'], 'pattern.png', { type: 'text/plain' }),
              wrongExtension: new File(['png'], 'pattern.txt', { type: 'application/octet-stream' }),
            };
            const form = new FormData();
            form.append('image', files.emptyMime);
            const request = new Request('http://local.test/api/v1/image-quality', { method: 'POST', body: form });
            const multipartBody = await request.text();
            console.log(JSON.stringify({
              emptyMimeWireType: multipartBody.includes('Content-Type: application/octet-stream'),
              results: Object.fromEntries(
                Object.entries(files).map(([name, file]) => [name, validateImageFile(file, maxBytes)]),
              ),
            }));
            """
        )
        self.assertTrue(payload["emptyMimeWireType"])
        self.assertEqual("", payload["results"]["emptyMime"])
        self.assertEqual("", payload["results"]["legacyPng"])
        self.assertEqual("", payload["results"]["binaryPng"])
        self.assertEqual("", payload["results"]["canonicalPng"])
        self.assertEqual("unsupported", payload["results"]["wrongMime"])
        self.assertEqual("unsupported", payload["results"]["wrongExtension"])

    def test_physical_uat_heic_metadata_is_rejected_as_unsupported(self):
        payload = run_browser_modules(
            """
            import { readFileSync } from 'node:fs';
            const module = (path) => import('data:text/javascript,' + encodeURIComponent(readFileSync(path, 'utf8')));
            const { validateImageFile } = await module('./pattern_translator/web/workflow_state.js');
            const maxBytes = 25 * 1024 * 1024;
            const heicHeader = Uint8Array.from([
              0x00, 0x00, 0x00, 0x20, 0x66, 0x74, 0x79, 0x70,
              0x68, 0x65, 0x69, 0x63, 0x00, 0x00, 0x00, 0x00,
            ]);
            const physicalFile = new File(
              [heicHeader],
              '18622931-C18E-431C-BA26-FBF91CAE3943_1_201_a.heic',
              { type: 'image/heic' },
            );
            const extensionPredicate = new File(
              [heicHeader], 'physical-uat.heic', { type: 'image/png' },
            );
            const mimePredicate = new File(
              [heicHeader], 'physical-uat.png', { type: 'image/heic' },
            );
            console.log(JSON.stringify({
              physical: validateImageFile(physicalFile, maxBytes),
              extension: validateImageFile(extensionPredicate, maxBytes),
              mime: validateImageFile(mimePredicate, maxBytes),
            }));
            """
        )
        self.assertEqual("unsupported", payload["physical"])
        self.assertEqual("unsupported", payload["extension"])
        self.assertEqual("unsupported", payload["mime"])

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

    def test_semantic_source_reset_discards_result_but_same_source_failures_preserve_it(self):
        payload = run_browser_modules(
            """
            import { readFileSync } from 'node:fs';
            const module = (path) => import('data:text/javascript,' + encodeURIComponent(readFileSync(path, 'utf8')));
            const { discardCompletedResult, invalidateQuality, invalidateRequest } = await module('./pattern_translator/web/workflow_state.js');
            const completedState = (file) => ({
              file, generation: 3, loading: false, controller: null,
              qualityGeneration: 2, qualityController: null,
              pngUrl: 'blob:overlay', txtUrl: 'blob:translation',
              diagnosticContext: { request_id: 'completed' },
              diagnosticLoading: true,
              diagnosticController: { abort() { this.aborted = true; } },
            });
            const snapshot = (state) => JSON.stringify({
              pngUrl: state.pngUrl,
              txtUrl: state.txtUrl,
              diagnosticContext: state.diagnosticContext,
            });

            const removeState = completedState({ name: 'old.png' });
            const removeController = removeState.diagnosticController;
            const removeRevoked = [];
            discardCompletedResult(removeState, (url) => removeRevoked.push(url));
            removeState.file = null;

            const replacementState = completedState({ name: 'old.png' });
            const replacementRevoked = [];
            discardCompletedResult(replacementState, (url) => replacementRevoked.push(url));
            replacementState.file = { name: 'new.png' };

            const sameSourceState = completedState({ name: 'same.png' });
            const beforeFailure = snapshot(sameSourceState);
            invalidateRequest(sameSourceState);
            invalidateQuality(sameSourceState);
            const afterFailure = snapshot(sameSourceState);

            console.log(JSON.stringify({
              removeCleared: removeState.file === null
                && removeState.pngUrl === null
                && removeState.txtUrl === null
                && removeState.diagnosticContext === null,
              removeCleanup: removeController.aborted
                && JSON.stringify(removeRevoked.sort()) === JSON.stringify(['blob:overlay', 'blob:translation'].sort()),
              replacementCleared: replacementState.file.name === 'new.png'
                && replacementState.pngUrl === null
                && replacementState.txtUrl === null
                && replacementState.diagnosticContext === null,
              replacementCleanup: JSON.stringify(replacementRevoked.sort()) === JSON.stringify(['blob:overlay', 'blob:translation'].sort()),
              sameSourceFailurePreserved: beforeFailure === afterFailure,
            }));
            """
        )
        self.assertTrue(payload["removeCleared"])
        self.assertTrue(payload["removeCleanup"])
        self.assertTrue(payload["replacementCleared"])
        self.assertTrue(payload["replacementCleanup"])
        self.assertTrue(payload["sameSourceFailurePreserved"])

    def test_quality_identity_confirmation_invalidation_and_duplicate_guards(self):
        payload = run_browser_modules(
            """
            import { readFileSync } from 'node:fs';
            const module = (path) => import('data:text/javascript,' + encodeURIComponent(readFileSync(path, 'utf8')));
            const {
              applyQualityResponse, beginTranslation, canTranslate,
              confirmPoorQuality, forceRunForCurrentQuality, hasCurrentQuality,
              invalidateQuality, invalidateRequest, isCurrentQualityRequest,
              qualityIdentity, translationFormEntries,
            } = await module('./pattern_translator/web/workflow_state.js');
            const fileA = { name: 'a.jpg' }, fileB = { name: 'b.jpg' };
            const poor = {
              area_mode: 'Whole Pattern', crop_box: [0, 0, 1500, 900],
              quality: {
                level: 'poor', label: 'Poor', requires_confirmation: true,
                metrics: { width_px: 1500, height_px: 900 },
                errors: ['blurry'], warnings: [],
              },
            };
            const state = {
              file: fileA, source: 'English — US', target: 'Japanese',
              area: 'Whole Pattern', crop: null, generation: 4, loading: false,
              controller: null, qualityGeneration: 7, qualityLoading: false,
              qualityController: null, qualityAssessment: null, qualityFile: null,
              qualityArea: null, qualityCrop: null, qualityConfirmed: false,
              qualityError: false, completedResult: { id: 'old-result' },
              pngUrl: 'old-png', txtUrl: 'old-txt', diagnosticContext: { id: 'old-report' },
            };
            const wholeIdentity = qualityIdentity(state);
            const appliedPoor = applyQualityResponse(state, poor, wholeIdentity);
            const blockedBeforeConfirmation = !canTranslate(state);
            confirmPoorQuality(state);
            const allowedAfterConfirmation = canTranslate(state);
            const forceForm = translationFormEntries(state).at(-1);
            state.target = 'Traditional Chinese';
            const retainedAfterLanguage = hasCurrentQuality(state) && forceRunForCurrentQuality(state);

            const firstController = new AbortController();
            const firstToken = beginTranslation(state, firstController);
            const secondToken = beginTranslation(state, new AbortController());
            const duplicateRequestCount = [firstToken, secondToken].filter((value) => value !== null).length;
            state.loading = false;

            const staleToken = state.qualityGeneration;
            const staleIdentity = qualityIdentity(state);
            invalidateQuality(state);
            state.file = fileB;
            const staleAfterReplacement = isCurrentQualityRequest(state, staleToken, staleIdentity);
            const replacementCleared = !hasCurrentQuality(state) && !forceRunForCurrentQuality(state);

            state.file = fileA;
            state.area = 'Select Area';
            state.crop = [10, 20, 210, 220];
            const cropIdentity = qualityIdentity(state);
            const cropPoor = { ...poor, area_mode: 'Select Area', crop_box: [...state.crop] };
            applyQualityResponse(state, cropPoor, cropIdentity);
            confirmPoorQuality(state);
            state.crop = [11, 20, 210, 220];
            const changedCropCleared = !hasCurrentQuality(state) && !forceRunForCurrentQuality(state);

            const oldResultBeforeFailures = JSON.stringify({
              completedResult: state.completedResult,
              pngUrl: state.pngUrl,
              txtUrl: state.txtUrl,
              diagnosticContext: state.diagnosticContext,
            });
            invalidateRequest(state);
            invalidateQuality(state);
            applyQualityResponse(state, { malformed: true }, qualityIdentity(state));
            const oldResultAfterFailures = JSON.stringify({
              completedResult: state.completedResult,
              pngUrl: state.pngUrl,
              txtUrl: state.txtUrl,
              diagnosticContext: state.diagnosticContext,
            });

            console.log(JSON.stringify({
              appliedPoor, blockedBeforeConfirmation, allowedAfterConfirmation,
              forceForm, retainedAfterLanguage, duplicateRequestCount,
              staleAfterReplacement, replacementCleared, changedCropCleared,
              previousResultPreserved: oldResultBeforeFailures === oldResultAfterFailures,
            }));
            """
        )
        self.assertTrue(payload["appliedPoor"])
        self.assertTrue(payload["blockedBeforeConfirmation"])
        self.assertTrue(payload["allowedAfterConfirmation"])
        self.assertEqual(["force_run", "true"], payload["forceForm"])
        self.assertTrue(payload["retainedAfterLanguage"])
        self.assertEqual(1, payload["duplicateRequestCount"])
        self.assertFalse(payload["staleAfterReplacement"])
        self.assertTrue(payload["replacementCleared"])
        self.assertTrue(payload["changedCropCleared"])
        self.assertTrue(payload["previousResultPreserved"])

    def test_quality_response_validation_and_stale_crop_protection(self):
        payload = run_browser_modules(
            """
            import { readFileSync } from 'node:fs';
            const module = (path) => import('data:text/javascript,' + encodeURIComponent(readFileSync(path, 'utf8')));
            const {
              applyQualityResponse, hasCurrentQuality, isCurrentQualityRequest,
              isValidQualityResponse, isValidTranslationResponse, qualityIdentity,
            } = await module('./pattern_translator/web/workflow_state.js');
            const file = { name: 'crop.png' };
            const state = {
              file, area: 'Select Area', crop: [40, 30, 140, 110],
              source: 'English — US', target: 'Japanese',
              qualityGeneration: 2, qualityAssessment: null, qualityFile: null,
              qualityArea: null, qualityCrop: null, qualityConfirmed: false,
            };
            const identity = qualityIdentity(state);
            const valid = {
              area_mode: 'Select Area', crop_box: [40, 30, 140, 110],
              quality: {
                level: 'fair', label: 'Fair', requires_confirmation: false,
                metrics: { width_px: 100, height_px: 80 },
                errors: [], warnings: ['soft'],
              },
            };
            const wrongCrop = { ...valid, crop_box: [41, 30, 140, 110] };
            const malformed = { ...valid, quality: { level: 'fair' } };
            const translation = {
              ...valid, request_id: 'request-1', source_mode: state.source,
              output_mode: state.target, readable_translation: 'translated',
              translation_txt: 'translated',
              overlay_png: { media_type: 'image/png', base64: 'cG5n' },
              diagnostic_context: null,
            };
            const validAccepted = isValidQualityResponse(valid, identity)
              && applyQualityResponse(state, valid, identity)
              && hasCurrentQuality(state);
            state.crop = [41, 30, 140, 110];
            console.log(JSON.stringify({
              validAccepted,
              wrongCropRejected: !isValidQualityResponse(wrongCrop, identity),
              malformedRejected: !isValidQualityResponse(malformed, identity),
              validTranslation: isValidTranslationResponse(translation, state, identity),
              malformedTranslationRejected: !isValidTranslationResponse(
                { ...translation, translation_txt: null }, state, identity,
              ),
              staleAfterCropChange: isCurrentQualityRequest(state, 2, identity),
              assessmentUnboundAfterCropChange: !hasCurrentQuality(state),
            }));
            """
        )
        self.assertTrue(payload["validAccepted"])
        self.assertTrue(payload["wrongCropRejected"])
        self.assertTrue(payload["malformedRejected"])
        self.assertTrue(payload["validTranslation"])
        self.assertTrue(payload["malformedTranslationRejected"])
        self.assertFalse(payload["staleAfterCropChange"])
        self.assertTrue(payload["assessmentUnboundAfterCropChange"])

    def test_quality_ui_strings_exist_with_exact_four_language_copy(self):
        payload = run_browser_modules(
            """
            import { readFileSync } from 'node:fs';
            const module = (path) => import('data:text/javascript,' + encodeURIComponent(readFileSync(path, 'utf8')));
            const { stringsFor } = await module('./pattern_translator/web/translations.js');
            const languages = ['en', 'zh-Hant', 'zh-Hans', 'ja'];
            console.log(JSON.stringify(languages.map((lang) => {
              const text = stringsFor(lang);
              return [
                text.qualityGood, text.qualityFair, text.qualityPoor,
                text.qualityGoodMessage, text.qualityFairMessage, text.qualityPoorMessage,
                text.qualityBlockWarning, text.forceOcr, text.qualityAssessmentError,
              ];
            })));
            """
        )
        self.assertEqual(
            [
                [
                    "🟢 Good", "🟡 Fair", "🔴 Poor",
                    "Image quality looks suitable for OCR.",
                    "OCR may contain some errors.",
                    "Image quality may affect OCR accuracy.",
                    "OCR is likely to be unreliable with this image. A clearer crop is strongly recommended. You can still force a test run below for checking.",
                    "Run OCR anyway",
                    "Image quality could not be assessed. Please try again.",
                ],
                [
                    "🟢 良好", "🟡 尚可", "🔴 不理想",
                    "圖片品質適合文字辨識。",
                    "辨識結果可能有一些錯誤。",
                    "圖片品質可能影響辨識準確度。",
                    "這張圖片的辨識結果可能不可靠。建議先使用更清晰的裁剪範圍；你仍可強制測試。",
                    "仍然開始文字辨識",
                    "無法評估圖片品質，請再試一次。",
                ],
                [
                    "🟢 良好", "🟡 尚可", "🔴 不理想",
                    "图片质量适合文字识别。",
                    "识别结果可能有一些错误。",
                    "图片质量可能影响识别准确度。",
                    "这张图片的识别结果可能不可靠。建议先使用更清晰的裁剪范围；你仍可强制测试。",
                    "仍然开始文字识别",
                    "无法评估图片质量，请再试一次。",
                ],
                [
                    "🟢 良好", "🟡 やや注意", "🔴 不十分",
                    "OCRに適した画像です。",
                    "OCR結果に一部誤りが出る可能性があります。",
                    "画像品質がOCR精度に影響する可能性があります。",
                    "この画像ではOCRが不安定になる可能性があります。より鮮明な切り抜きをおすすめしますが、テストとして強制実行できます。",
                    "それでもOCRを実行",
                    "画像品質を確認できませんでした。もう一度お試しください。",
                ],
            ],
            payload,
        )

    def test_drag_hint_remains_localized_on_desktop_and_hides_on_touch_layout(self):
        html = (REPO_ROOT / "pattern_translator" / "web" / "index.html").read_text(encoding="utf-8")
        css = (REPO_ROOT / "pattern_translator" / "web" / "styles.css").read_text(encoding="utf-8")
        hints = run_browser_modules(
            """
            import { readFileSync } from 'node:fs';
            const module = (path) => import('data:text/javascript,' + encodeURIComponent(readFileSync(path, 'utf8')));
            const { stringsFor } = await module('./pattern_translator/web/translations.js');
            console.log(JSON.stringify(['en', 'zh-Hant', 'zh-Hans', 'ja'].map((lang) => stringsFor(lang).dropHint)));
            """
        )

        self.assertIn('class="drop-hint" data-i18n="dropHint"', html)
        self.assertEqual(
            [
                "Or drag and drop an image here",
                "或將圖片拖曳到這裡",
                "或将图片拖到这里",
                "または画像をここにドラッグ＆ドロップ",
            ],
            hints,
        )
        self.assertIn(
            "@media (hover:none) and (pointer:coarse){.drop-hint{display:none!important}}",
            css,
        )

    def test_translation_failures_do_not_clear_completed_browser_result(self):
        app_source = (
            REPO_ROOT / "pattern_translator" / "web" / "app.js"
        ).read_text(encoding="utf-8")
        start = app_source.index("function invalidateTranslationRequest()")
        end = app_source.index("\nfunction clearCompletedResult()", start)
        invalidation_source = app_source[start:end]
        translate_start = app_source.index("async function translate()")
        translate_end = app_source.index("\nfunction showResult(", translate_start)
        translate_source = app_source[translate_start:translate_end]

        self.assertNotIn('clearObjectUrl("pngUrl")', invalidation_source)
        self.assertNotIn('clearObjectUrl("txtUrl")', invalidation_source)
        self.assertNotIn("diagnosticContext = null", invalidation_source)
        self.assertNotIn('"result-section").hidden = true', invalidation_source)
        self.assertNotIn("invalidateTranslationRequest()", translate_source)
        self.assertIn("showResult(body)", translate_source)

    def test_diagnostic_ui_strings_exist_in_all_four_languages(self):
        payload = run_browser_modules(
            """
            import { readFileSync } from 'node:fs';
            const module = (path) => import('data:text/javascript,' + encodeURIComponent(readFileSync(path, 'utf8')));
            const { stringsFor } = await module('./pattern_translator/web/translations.js');
            const languages = ['en', 'zh-Hant', 'zh-Hans', 'ja'];
            console.log(JSON.stringify(languages.map((lang) => {
              const text = stringsFor(lang);
              return [text.downloadDiagnostic, text.diagnosticLoading, text.diagnosticError];
            })));
            """
        )
        self.assertEqual(
            [
                [
                    "Download Diagnostic Report",
                    "Preparing Diagnostic Report…",
                    "The Diagnostic Report could not be generated. Your translation is still available.",
                ],
                [
                    "下載診斷報告",
                    "正在準備診斷報告……",
                    "無法產生診斷報告。你的翻譯結果仍然可用。",
                ],
                [
                    "下载诊断报告",
                    "正在准备诊断报告……",
                    "无法生成诊断报告。你的翻译结果仍然可用。",
                ],
                [
                    "診断レポートをダウンロード",
                    "診断レポートを準備しています……",
                    "診断レポートを生成できませんでした。翻訳結果は引き続き利用できます。",
                ],
            ],
            payload,
        )

    def test_diagnostic_request_runtime_is_repeatable_and_stale_safe(self):
        payload = run_browser_modules(
            """
            import { readFileSync } from 'node:fs';
            const module = (path) => import('data:text/javascript,' + encodeURIComponent(readFileSync(path, 'utf8')));
            const { diagnosticFilename, isCurrentDiagnosticRequest, postDiagnosticReport } = await module('./pattern_translator/web/workflow_state.js');
            const context = { schema_version: 1, result: { area_mode: 'Whole Pattern' } };
            const state = { generation: 4, diagnosticContext: context };
            const calls = [];
            const fetchImpl = async (url, options) => {
              calls.push({ url, method: options.method, headers: options.headers, body: JSON.parse(options.body), signal: Boolean(options.signal) });
              return {
                ok: true,
                headers: { get: (name) => name === 'content-disposition' ? 'attachment; filename="safe-report.txt"' : '' },
              };
            };
            const controller = new AbortController();
            const first = await postDiagnosticReport(fetchImpl, context, 'ja', controller.signal);
            await postDiagnosticReport(fetchImpl, context, 'ja', controller.signal);
            const currentBefore = isCurrentDiagnosticRequest(state, 4, context);
            state.generation += 1;
            const currentAfterGeneration = isCurrentDiagnosticRequest(state, 4, context);
            state.generation = 4;
            state.diagnosticContext = { schema_version: 1 };
            const currentAfterReplacement = isCurrentDiagnosticRequest(state, 4, context);
            console.log(JSON.stringify({
              calls,
              filename: diagnosticFilename(first),
              fallback: diagnosticFilename({ headers: { get: () => '' } }),
              currentBefore,
              currentAfterGeneration,
              currentAfterReplacement,
            }));
            """
        )
        self.assertEqual(2, len(payload["calls"]))
        for call in payload["calls"]:
            self.assertEqual("/api/v1/diagnostic-report", call["url"])
            self.assertEqual("POST", call["method"])
            self.assertEqual("application/json", call["headers"]["Content-Type"])
            self.assertEqual("ja", call["body"]["ui_lang"])
            self.assertEqual(1, call["body"]["diagnostic_context"]["schema_version"])
            self.assertTrue(call["signal"])
        self.assertEqual("safe-report.txt", payload["filename"])
        self.assertEqual("PatternOCR_DiagnosticReport.txt", payload["fallback"])
        self.assertTrue(payload["currentBefore"])
        self.assertFalse(payload["currentAfterGeneration"])
        self.assertFalse(payload["currentAfterReplacement"])

    def test_diagnostic_download_blob_handling_is_isolated(self):
        app_source = (
            REPO_ROOT / "pattern_translator" / "web" / "app.js"
        ).read_text(encoding="utf-8")
        html_source = (
            REPO_ROOT / "pattern_translator" / "web" / "index.html"
        ).read_text(encoding="utf-8")
        start = app_source.index("async function downloadDiagnostic()")
        end = app_source.index("\nfunction track(", start)
        diagnostic_source = app_source[start:end]

        self.assertIn('id="diagnostic-download"', html_source)
        self.assertIn('id="diagnostic-status"', html_source)
        self.assertIn("postDiagnosticReport(", diagnostic_source)
        self.assertGreaterEqual(
            diagnostic_source.count("isCurrentDiagnosticRequest(state, token, diagnosticContext)"),
            4,
        )
        self.assertIn("new Blob([reportText]", diagnostic_source)
        self.assertIn("anchor.click()", diagnostic_source)
        self.assertIn("URL.revokeObjectURL(reportUrl)", diagnostic_source)
        self.assertIn("setDiagnosticMessage(text.diagnosticError)", diagnostic_source)
        self.assertNotIn('clearObjectUrl("pngUrl")', diagnostic_source)
        self.assertNotIn('clearObjectUrl("txtUrl")', diagnostic_source)
        self.assertNotIn('$("result-section").hidden = true', diagnostic_source)
        self.assertNotIn("showResult(", diagnostic_source)

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
            const {{ displayBoxToImage, displayBoxToOriginal, normalizedCropBox, readExifOrientation, resizeCropBox }} = await module('./pattern_translator/web/crop_coordinates.js');
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
              orientedImageCrop: displayBoxToImage({{left:10.2,top:11.1,right:30.8,bottom:31.9}}, 59, 101),
              orientedImageClamped: displayBoxToImage({{left:-5,top:-2,right:70,bottom:110}}, 59, 101),
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
        self.assertEqual([10, 11, 31, 32], payload["orientedImageCrop"])
        self.assertEqual([0, 0, 59, 101], payload["orientedImageClamped"])
        self.assertEqual({"left": 20, "top": 10, "width": 50, "height": 30}, payload["leftAnchored"])
        self.assertEqual({"left": 20, "top": 10, "width": 30, "height": 50}, payload["topAnchored"])
        self.assertEqual({"left": 0, "top": 50, "width": 50, "height": 50}, payload["normalised"])
        self.assertEqual({"2": 2, "4": 4, "5": 5, "7": 7}, payload["exif"])


if __name__ == "__main__":
    unittest.main()
