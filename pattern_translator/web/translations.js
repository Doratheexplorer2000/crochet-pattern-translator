export const SUPPORTED_UI_LANGS = new Set(["en", "zh-Hant", "zh-Hans", "ja"]);

const english = {
  brand: "Crochet Intelligence", title: "Crochet Pattern Translator",
  subtitle: "Pattern OCR Translator (Beta)",
  back: "Back to Crochet Intelligence", uploadInstruction: "Choose a pattern image",
  choose: "Choose image", dropHint: "Or drag and drop an image here", dropActive: "Drop the image here",
  selected: "Selected image", replace: "Replace", remove: "Remove",
  source: "Pattern language / terminology", target: "Translate result to", area: "Translation area", areaLabel: "Area to Translate",
  chooseOption: "Choose an option",
  whole: "Whole Pattern", select: "Select Area", areaTip: "💡 Select Area is optional and experimental. Use it when you need to translate only part of an image.", cropHelp: "Drag the rectangle around the text you want translated.\n\nUse the Precision Pad to fine-tune the highlighted border.",
  startOver: "Start Over", reset: "Reset", useArea: "Use This Area", editArea: "Edit Selection",
  translate: "Translate", translating: "Running OCR and building overlay translation.", runningAction: "⏳ OCR Running...",
  qualityGood: "🟢 Good", qualityFair: "🟡 Fair", qualityPoor: "🔴 Poor",
  qualityGoodMessage: "Image quality looks suitable for OCR.", qualityFairMessage: "OCR may contain some errors.", qualityPoorMessage: "Image quality may affect OCR accuracy.",
  qualityBlockWarning: "OCR is likely to be unreliable with this image. A clearer crop is strongly recommended. You can still force a test run below for checking.",
  forceOcr: "Run OCR anyway", qualityAssessing: "Assessing image quality…", qualityAssessmentError: "Image quality could not be assessed. Please try again.",
  overlay: "Overlay translation", overlayCaption: "Smart overlay: short translations are shown directly; long/colliding translations use numbered markers.", lines: "Line-by-line Translation", translatedLines: "Translated OCR lines", downloadPng: "Download Overlay Image PNG",
  downloadTxt: "Download Translation TXT", downloadDiagnostic: "Download Diagnostic Report", diagnosticLoading: "Preparing Diagnostic Report…", diagnosticError: "The Diagnostic Report could not be generated. Your translation is still available.", feedback: "🐞 Report a Problem", feedbackHelp: "If something doesn’t look right, describe the problem and optionally attach screenshots.", feedbackAction: "Open Feedback Form",
  reading: "Reading image…", originalImage: "Original image", cropConfirmed: "This selected area will be used for OCR. Tap Edit Selection to change it.", cropPreviewCaption: "This cropped area will be sent to OCR", errorEmpty: "This file is empty. Please choose another image.",
  errorUnsupported: "This file cannot be used. Please choose a JPG, JPEG, PNG or WebP image.",
  errorLarge: "This image is too large. Please choose an image smaller than 25 MB.",
  errorUnreadable: "This file could not be read. Please choose another image.",
  errorCrop: "Please select an area before translating, or switch to Whole Pattern.",
  errorNetwork: "The translation service could not be reached. Please try again.",
  errorGeneric: "Translation failed. Please try again.", errorValidation: "Please check the selected image and translation settings.",
  errorRequest: "Translation failed. Reference: ", success: "Translation complete.",
  imageAlt: "Crochet pattern image for area selection", selection: "Selected translation area",
  resizeTop: "Resize top edge", resizeRight: "Resize right edge", resizeBottom: "Resize bottom edge", resizeLeft: "Resize left edge",
  moveControls: "Move precision controls", moveUp: "Move selected edge upward", moveDown: "Move selected edge downward",
  moveLeft: "Move selected edge left", moveRight: "Move selected edge right",
  sourceHintUs: "💡 Most crochet patterns use US terminology.\nIf the stitch names don’t look right, try switching to English (UK).", sourceHintUk: "💡 UK terminology is less common.\nIf the stitch names don’t look right, try switching to English (US), as most crochet patterns use US terminology.", targetHintUs: "💡 US terminology is the standard used by most crochet patterns.", targetHintUk: "💡 Choose UK terminology only if you specifically need UK stitch names.",
};

const translations = {
  en: english,
  "zh-Hant": {
    ...english, title: "鈎織翻譯器", subtitle: "圖樣文字辨識翻譯器（測試版）",
    back: "返回 Crochet Intelligence", uploadInstruction: "選擇要翻譯的圖樣圖片", choose: "選擇圖片",
    dropHint: "或將圖片拖曳到這裡", dropActive: "在此放下圖片", selected: "已選擇圖片", replace: "更換", remove: "移除",
    source: "圖樣語言／術語", target: "翻譯結果語言", area: "翻譯範圍", areaLabel: "要翻譯的範圍", whole: "整個圖樣", select: "選取範圍",
    chooseOption: "請選擇",
    areaTip: "💡 選取範圍是選用的實驗功能。需要只翻譯圖片的一部分時可以使用。", cropHelp: "請拖拉方框，框住要翻譯的文字。\n\n使用精細調整控制器微調反白顯示的邊界。", startOver: "重新開始", reset: "重設",
    useArea: "使用此範圍", editArea: "編輯範圍", translate: "翻譯", translating: "正在辨識圖片文字並產生翻譯……", runningAction: "⏳ 正在辨識文字…",
    qualityGood: "🟢 良好", qualityFair: "🟡 尚可", qualityPoor: "🔴 不理想",
    qualityGoodMessage: "圖片品質適合文字辨識。", qualityFairMessage: "辨識結果可能有一些錯誤。", qualityPoorMessage: "圖片品質可能影響辨識準確度。",
    qualityBlockWarning: "這張圖片的辨識結果可能不可靠。建議先使用更清晰的裁剪範圍；你仍可強制測試。",
    forceOcr: "仍然開始文字辨識", qualityAssessing: "正在評估圖片品質……", qualityAssessmentError: "無法評估圖片品質，請再試一次。",
    overlay: "圖片翻譯結果", overlayCaption: "短翻譯會直接顯示在圖片上；較長或重疊的翻譯會用編號標記。", lines: "逐行翻譯", translatedLines: "已翻譯的文字辨識行", downloadPng: "下載翻譯圖片 PNG",
    downloadTxt: "下載文字翻譯 TXT", downloadDiagnostic: "下載診斷報告", diagnosticLoading: "正在準備診斷報告……", diagnosticError: "無法產生診斷報告。你的翻譯結果仍然可用。", feedback: "🐞 回報問題", feedbackHelp: "如果翻譯看起來不太對，請描述問題，也可以附上截圖。", feedbackAction: "開啟意見表單", reading: "正在讀取圖片……", originalImage: "原始圖片", cropConfirmed: "文字辨識會使用這個已選範圍。如需修改，請點選「編輯範圍」。", cropPreviewCaption: "這個裁剪範圍會送去文字辨識",
    errorEmpty: "這個檔案是空的，請選擇其他圖片。", errorUnsupported: "這個檔案無法使用。請選擇 JPG、JPEG、PNG 或 WebP 圖片。",
    errorLarge: "圖片過大，請選擇小於 25 MB 的圖片。", errorUnreadable: "無法讀取這個檔案，請選擇其他圖片。",
    errorCrop: "請先選取範圍再翻譯，或切換回整個圖樣。", errorNetwork: "無法連線到翻譯服務，請再試一次。",
    errorGeneric: "翻譯失敗，請再試一次。", errorValidation: "請檢查所選圖片與翻譯設定。", errorRequest: "翻譯失敗。參考編號：", success: "翻譯完成。",
    resizeTop: "調整上方邊緣", resizeRight: "調整右方邊緣", resizeBottom: "調整下方邊緣", resizeLeft: "調整左方邊緣",
    moveControls: "移動精細調整控制器", moveUp: "向上移動選取邊緣", moveDown: "向下移動選取邊緣", moveLeft: "向左移動選取邊緣", moveRight: "向右移動選取邊緣",
    sourceHintUs: "💡 大部分鈎織圖樣使用美式術語。\n如果針法名稱看起來不對，可以試試切換到英文（英式）。", sourceHintUk: "💡 英式術語較少見。\n如果針法名稱看起來不對，可以試試切換到英文（美式），因為大部分鈎織圖樣使用美式術語。", targetHintUs: "💡 美式術語是大部分鈎織圖樣使用的標準。", targetHintUk: "💡 只有在你特別需要英式針法名稱時，才建議選擇英式術語。",
  },
  "zh-Hans": {
    ...english, title: "钩织翻译器", subtitle: "图样文字识别翻译器（测试版）",
    back: "返回 Crochet Intelligence", uploadInstruction: "选择要翻译的图样图片", choose: "选择图片",
    dropHint: "或将图片拖到这里", dropActive: "在此放下图片", selected: "已选择图片", replace: "更换", remove: "移除",
    source: "图样语言／术语", target: "翻译结果语言", area: "翻译范围", areaLabel: "要翻译的范围", whole: "整个图样", select: "选取范围",
    chooseOption: "请选择",
    areaTip: "💡 选取范围是选用的实验功能。需要只翻译图片的一部分时可以使用。", cropHelp: "请拖拉方框，框住要翻译的文字。\n\n使用精细调整控制器微调高亮显示的边界。", startOver: "重新开始", reset: "重置",
    useArea: "使用此范围", editArea: "编辑范围", translate: "翻译", translating: "正在识别图片文字并生成翻译……", runningAction: "⏳ 正在识别文字…",
    qualityGood: "🟢 良好", qualityFair: "🟡 尚可", qualityPoor: "🔴 不理想",
    qualityGoodMessage: "图片质量适合文字识别。", qualityFairMessage: "识别结果可能有一些错误。", qualityPoorMessage: "图片质量可能影响识别准确度。",
    qualityBlockWarning: "这张图片的识别结果可能不可靠。建议先使用更清晰的裁剪范围；你仍可强制测试。",
    forceOcr: "仍然开始文字识别", qualityAssessing: "正在评估图片质量……", qualityAssessmentError: "无法评估图片质量，请再试一次。",
    overlay: "图片翻译结果", overlayCaption: "短翻译会直接显示在图片上；较长或重叠的翻译会用编号标记。", lines: "逐行翻译", translatedLines: "已翻译的文字识别行", downloadPng: "下载翻译图片 PNG",
    downloadTxt: "下载文字翻译 TXT", downloadDiagnostic: "下载诊断报告", diagnosticLoading: "正在准备诊断报告……", diagnosticError: "无法生成诊断报告。你的翻译结果仍然可用。", feedback: "🐞 回报问题", feedbackHelp: "如果翻译看起来不太对，请描述问题，也可以附上截图。", feedbackAction: "打开反馈表单", reading: "正在读取图片……", originalImage: "原始图片", cropConfirmed: "文字识别会使用这个已选范围。如需修改，请点选“编辑范围”。", cropPreviewCaption: "这个裁剪范围会送去文字识别",
    errorEmpty: "这个文件是空的，请选择其他图片。", errorUnsupported: "这个文件无法使用。请选择 JPG、JPEG、PNG 或 WebP 图片。",
    errorLarge: "图片过大，请选择小于 25 MB 的图片。", errorUnreadable: "无法读取这个文件，请选择其他图片。",
    errorCrop: "请先选择范围再翻译，或切换回整个图样。", errorNetwork: "无法连接到翻译服务，请再试一次。",
    errorGeneric: "翻译失败，请再试一次。", errorValidation: "请检查所选图片与翻译设置。", errorRequest: "翻译失败。参考编号：", success: "翻译完成。",
    resizeTop: "调整上方边缘", resizeRight: "调整右方边缘", resizeBottom: "调整下方边缘", resizeLeft: "调整左方边缘",
    moveControls: "移动精细调整控制器", moveUp: "向上移动选定边缘", moveDown: "向下移动选定边缘", moveLeft: "向左移动选定边缘", moveRight: "向右移动选定边缘",
    sourceHintUs: "💡 大部分钩织图样使用美式术语。\n如果针法名称看起来不对，可以试试切换到英文（英式）。", sourceHintUk: "💡 英式术语较少见。\n如果针法名称看起来不对，可以试试切换到英文（美式），因为大部分钩织图样使用美式术语。", targetHintUs: "💡 美式术语是大部分钩织图样使用的标准。", targetHintUk: "💡 只有在你特别需要英式针法名称时，才建议选择英式术语。",
  },
  ja: {
    ...english, title: "かぎ針編み翻訳", subtitle: "パターンOCR翻訳（ベータ版）",
    back: "Crochet Intelligence に戻る", uploadInstruction: "翻訳するパターン画像を選んでください", choose: "画像を選ぶ",
    dropHint: "または画像をここにドラッグ＆ドロップ", dropActive: "ここに画像をドロップ", selected: "選択した画像", replace: "変更", remove: "削除",
    source: "パターンの言語／用語", target: "翻訳先", area: "翻訳する範囲", areaLabel: "翻訳する範囲", whole: "パターン全体", select: "範囲を選択",
    chooseOption: "選択してください",
    areaTip: "💡 範囲選択は任意の実験的な機能です。画像の一部だけを翻訳したい場合に使用してください。", cropHelp: "翻訳したい文字を囲むように四角をドラッグしてください。\n\n微調整コントローラーを使って、強調表示された境界線を細かく調整してください。", startOver: "選び直す", reset: "リセット",
    useArea: "この範囲を使う", editArea: "選択範囲を編集", translate: "翻訳", translating: "画像の文字を認識して翻訳を作成しています……", runningAction: "⏳ OCR 実行中…",
    qualityGood: "🟢 良好", qualityFair: "🟡 やや注意", qualityPoor: "🔴 不十分",
    qualityGoodMessage: "OCRに適した画像です。", qualityFairMessage: "OCR結果に一部誤りが出る可能性があります。", qualityPoorMessage: "画像品質がOCR精度に影響する可能性があります。",
    qualityBlockWarning: "この画像ではOCRが不安定になる可能性があります。より鮮明な切り抜きをおすすめしますが、テストとして強制実行できます。",
    forceOcr: "それでもOCRを実行", qualityAssessing: "画像品質を確認しています……", qualityAssessmentError: "画像品質を確認できませんでした。もう一度お試しください。",
    overlay: "画像上の翻訳", overlayCaption: "短い翻訳は画像上に直接表示されます。長い翻訳や重なる翻訳は番号で表示されます。", lines: "行ごとの翻訳", translatedLines: "翻訳されたOCR行", downloadPng: "翻訳画像PNGをダウンロード",
    downloadTxt: "翻訳テキストをダウンロード", downloadDiagnostic: "診断レポートをダウンロード", diagnosticLoading: "診断レポートを準備しています……", diagnosticError: "診断レポートを生成できませんでした。翻訳結果は引き続き利用できます。", feedback: "🐞 問題を報告", feedbackHelp: "翻訳が正しくないように見える場合は、問題の内容を入力し、必要に応じてスクリーンショットを添付してください。", feedbackAction: "フィードバックフォームを開く", reading: "画像を読み込んでいます……", originalImage: "元の画像", cropConfirmed: "この選択範囲が文字認識に使われます。変更する場合は「選択範囲を編集」をタップしてください。", cropPreviewCaption: "この切り抜き範囲が文字認識に送られます",
    errorEmpty: "このファイルは空です。別の画像を選んでください。", errorUnsupported: "このファイルは使用できません。JPG、JPEG、PNG、または WebP 画像を選んでください。",
    errorLarge: "画像が大きすぎます。25 MB 未満の画像を選んでください。", errorUnreadable: "このファイルを読み取れませんでした。別の画像を選んでください。",
    errorCrop: "翻訳前に範囲を選択するか、パターン全体に戻してください。", errorNetwork: "翻訳サービスに接続できません。もう一度お試しください。",
    errorGeneric: "翻訳に失敗しました。もう一度お試しください。", errorValidation: "選択した画像と翻訳設定を確認してください。", errorRequest: "翻訳に失敗しました。参照番号：", success: "翻訳が完了しました。",
    resizeTop: "上辺を調整", resizeRight: "右辺を調整", resizeBottom: "下辺を調整", resizeLeft: "左辺を調整",
    moveControls: "微調整コントローラーを移動", moveUp: "選択した辺を上へ移動", moveDown: "選択した辺を下へ移動", moveLeft: "選択した辺を左へ移動", moveRight: "選択した辺を右へ移動",
    sourceHintUs: "💡 ほとんどのかぎ針編みパターンは米式用語を使っています。\n針目名が合わない場合は、英語（英国式）に切り替えてみてください。", sourceHintUk: "💡 英国式用語は比較的少数派です。\n針目名が合わない場合は、ほとんどのパターンで使われる英語（米国式）に切り替えてみてください。", targetHintUs: "💡 米式用語は、ほとんどのかぎ針編みパターンで使われる標準的な用語です。", targetHintUk: "💡 英国式の針目名が特に必要な場合だけ、英国式用語を選んでください。",
  },
};

export function resolveUiLang(value, browserLanguages = []) {
  if (SUPPORTED_UI_LANGS.has(value)) return value;
  for (const language of browserLanguages) {
    const tag = String(language).toLowerCase().replace("_", "-");
    if (tag.startsWith("ja")) return "ja";
    if (tag.startsWith("zh")) return tag.includes("hans") || tag.includes("-cn") || tag.includes("-sg") ? "zh-Hans" : "zh-Hant";
  }
  return "en";
}

export function stringsFor(uiLang) {
  return translations[uiLang] || english;
}

export function modeLabelFor(mode, uiLang) {
  const labels = {
    "English — US": {
      en: "English — US", "zh-Hant": "美式英文",
      "zh-Hans": "英文 — 美式", ja: "英語 — 米国式",
    },
    "English — UK": {
      en: "English — UK", "zh-Hant": "英式英文",
      "zh-Hans": "英文 — 英式", ja: "英語 — 英国式",
    },
    "Traditional Chinese": {
      en: "Traditional Chinese", "zh-Hant": "繁體中文",
      "zh-Hans": "繁体中文", ja: "繁体字中国語",
    },
    "Simplified Chinese": {
      en: "Simplified Chinese", "zh-Hant": "簡體中文",
      "zh-Hans": "简体中文", ja: "簡体字中国語",
    },
    Japanese: {
      en: "Japanese", "zh-Hant": "日文", "zh-Hans": "日语", ja: "日本語",
    },
  };
  return labels[mode]?.[uiLang] || mode;
}
