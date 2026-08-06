# Crochet Intelligence UI Specification

## 1. Document Status

- Status: Living Design Specification
- Current phase: Approved Home Screen baseline
- Specification state: RC51 baseline approved after physical-iPhone Human Visual UAT; future refinements remain possible
- Scope: Crochet Intelligence shared UI foundation, beginning with the Crochet Pattern Translator home/upload screen
- Primary device target: Mobile phone
- Supported interface languages:
  - Traditional Chinese
  - Simplified Chinese
  - English
  - Japanese

This document records the design values approved for implementation now. It is not a final UI freeze; approved future refinements replace the corresponding active values.

---

## 2. Brand Direction

### Current Direction

**Warm Modern**

The interface should combine:

- modern software clarity
- warm neutral surfaces
- restrained crochet character
- calm and trustworthy presentation
- strong mobile usability

### Brand Attributes

- Calm
- Professional
- Warm
- Crafted
- Trustworthy
- Clear
- Productivity-first

### Design Principles

- Function before decoration.
- Trust before trend.
- Consistency before novelty.
- Mobile usability before desktop embellishment.
- The user's crochet pattern and translation result are the primary content.
- Interface colours should support content rather than compete with it.
- Crochet character should be expressed subtly, not through excessive decoration.
- Do not use red as the normal primary action colour.
- Red is reserved for destructive actions and errors.
- Avoid generic AI, gaming, cryptocurrency, developer-tool, and enterprise-dashboard styling.

---

## 3. Colour System

Status: **APPROVED CURRENT BASELINE**

### 3.1 Core Brand Colours

```css
:root {
  --ci-teal-700: #0F766E;
  --ci-teal-600: #13867D;
  --ci-teal-100: #DDEDEA;
  --ci-teal-050: #EAF4F2;
  --ci-terracotta-700: #C2613F;
  --ci-terracotta-500: #D97A5A;
  --ci-terracotta-100: #F6E8E3;
  --ci-terracotta-050: #FBEDE8;
}
```

Usage:

- `--ci-teal-700`: primary action, brand title, active controls, important links
- `--ci-teal-600`: hover or secondary brand emphasis
- `--ci-teal-100`: subtle selected state, chip background, soft highlight
- `--ci-teal-050`: very light supporting surface
- Terracotta must be used sparingly.
- Terracotta is an accent, not the default primary action colour.

### 3.2 Light Mode Neutrals

```css
:root {
  --ci-bg-light: #FAF9F7;
  --ci-surface-light: #FFFFFF;
  --ci-surface-subtle-light: #F2EEE9;
  --ci-border-light: #E7E3DE;
  --ci-text-primary-light: #1E1E20;
  --ci-text-secondary-light: #55565A;
  --ci-text-muted-light: #8A8D91;
  --ci-text-on-primary-light: #FFFFFF;
}
```

Usage:

- Page background: `--ci-bg-light`
- Main cards and controls: `--ci-surface-light`
- Secondary information areas: `--ci-surface-subtle-light`
- Default border and divider: `--ci-border-light`
- Main headings and body copy: `--ci-text-primary-light`
- Supporting copy: `--ci-text-secondary-light`
- Captions and metadata: `--ci-text-muted-light`

The Light Mode page background must remain warm off-white. Do not tint the entire page blue-green.

### 3.3 Dark Mode Neutrals

```css
@media (prefers-color-scheme: dark) {
  :root {
    --ci-bg-dark: #17191A;
    --ci-surface-dark: #202426;
    --ci-surface-subtle-dark: #292D2F;
    --ci-border-dark: #434A4D;
    --ci-text-primary-dark: #F4F3F1;
    --ci-text-secondary-dark: #C9C7C3;
    --ci-text-muted-dark: #999C9D;
    --ci-text-on-primary-dark: #FFFFFF;
    --ci-primary-dark: #2F928A;
    --ci-primary-hover-dark: #3AA49B;
    --ci-primary-soft-dark: #213B39;
  }
}
```

Dark Mode rules:

- Use charcoal, not pure black.
- Avoid large pure-black surfaces.
- Retain teal as the brand identifier.
- Ensure borders remain visible without becoming bright outlines.
- Maintain clear text contrast.
- Do not simply invert Light Mode colours.

### 3.4 Semantic Colours

```css
:root {
  --ci-success: #2E7D5B;
  --ci-warning: #D99A24;
  --ci-error: #D64545;
  --ci-info: #3A7BD5;
}
```

Usage:

- Success: completed operation or valid status
- Warning: action requiring attention
- Error: failure, invalid state, or destructive result
- Info: neutral informational status
- Do not use semantic colours as decorative brand colours.

### 3.5 Focus State

```css
:root {
  --ci-focus-ring: rgba(15, 118, 110, 0.28);
}
```

All keyboard-focusable and interactive controls must use:

```css
outline: 3px solid var(--ci-focus-ring);
outline-offset: 2px;
```

Do not remove focus indication.

---

## 4. Typography

Status: **APPROVED CURRENT BASELINE**

### 4.1 Font Families

Use one coordinated font family across the entire platform.

```css
:root {
  --ci-font-en: "Noto Sans";
  --ci-font-zh-hant: "Noto Sans TC";
  --ci-font-zh-hans: "Noto Sans SC";
  --ci-font-ja: "Noto Sans JP";
  --ci-font-fallback: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
```

Recommended language mappings:

```css
html[lang="en"] {
  font-family: "Noto Sans", var(--ci-font-fallback);
}

html[lang="zh-Hant"] {
  font-family: "Noto Sans TC", "Noto Sans", var(--ci-font-fallback);
}

html[lang="zh-Hans"] {
  font-family: "Noto Sans SC", "Noto Sans", var(--ci-font-fallback);
}

html[lang="ja"] {
  font-family: "Noto Sans JP", "Noto Sans", var(--ci-font-fallback);
}
```

Do not mix serif, handwriting, script, or decorative fonts into the application UI.

### 4.2 Font Weights

```css
:root {
  --ci-font-regular: 400;
  --ci-font-medium: 500;
  --ci-font-semibold: 600;
  --ci-font-bold: 700;
}
```

Avoid weights below 400 for normal UI text.

### 4.3 Mobile Type Scale

```css
:root {
  --ci-type-h1-size: 30px;
  --ci-type-h1-line: 36px;
  --ci-type-h1-weight: 700;
  --ci-type-h2-size: 22px;
  --ci-type-h2-line: 28px;
  --ci-type-h2-weight: 600;
  --ci-type-section-size: 18px;
  --ci-type-section-line: 26px;
  --ci-type-section-weight: 600;
  --ci-type-body-size: 16px;
  --ci-type-body-line: 24px;
  --ci-type-body-weight: 400;
  --ci-type-button-size: 17px;
  --ci-type-button-line: 24px;
  --ci-type-button-weight: 600;
  --ci-type-small-size: 14px;
  --ci-type-small-line: 20px;
  --ci-type-small-weight: 400;
  --ci-type-caption-size: 13px;
  --ci-type-caption-line: 18px;
  --ci-type-caption-weight: 400;
}
```

Initial mapping for the Pattern Translator home screen:

- Product title: H1
- Product subtitle: Body or Small, depending on the available width
- Upload-area heading: Section
- Primary button label: Button
- Privacy disclosure label: Body, Medium or Semibold
- Privacy disclosure body: Small

Typography rules:

- Main user-facing text must normally remain at least 16px.
- Supporting metadata may use 14px.
- Avoid 12px text for important information.
- Do not use all-uppercase Chinese or Japanese text.
- English uppercase should be limited to very short labels.
- Avoid excessive letter spacing in Chinese and Japanese.
- Do not fake font weight with text shadows.

---

## 5. Spacing System

Status: **APPROVED CURRENT BASELINE**

Use an 8px-oriented spacing system with a small 4px increment.

```css
:root {
  --ci-space-1: 4px;
  --ci-space-2: 8px;
  --ci-space-3: 12px;
  --ci-space-4: 16px;
  --ci-space-5: 24px;
  --ci-space-6: 32px;
  --ci-space-7: 48px;
  --ci-space-8: 64px;
}
```

Mobile Page Spacing:

```css
:root {
  --ci-page-padding-mobile: 20px;
  --ci-section-gap-mobile: 32px;
  --ci-component-gap-mobile: 16px;
  --ci-inline-gap-mobile: 12px;
}
```

Recommended home-screen spacing:

- Top safe-area to product header: 24px minimum
- Product title to subtitle: 4px visual separation
- Product header to upload card: 32px
- Upload-card internal vertical padding: 24px
- Upload-card internal horizontal padding: 20px
- Upload heading to primary button: 20px
- Upload card to privacy disclosure: 24px
- Main content bottom safe space: at least 32px

Do not create large unused gaps merely for decoration.

Space reserved for future GIF/JPEG guidance is not part of the current upload card specification.

---

## 6. Border Radius

Status: **APPROVED CURRENT BASELINE**

```css
:root {
  --ci-radius-sm: 8px;
  --ci-radius-md: 12px;
  --ci-radius-lg: 16px;
  --ci-radius-xl: 24px;
}
```

Usage:

- Small chips and compact controls: 8px
- Buttons and form controls: 12px
- Standard cards and upload area: 16px
- Large marketing surfaces only: 24px

Do not use pill-shaped buttons by default.

---

## 7. Borders and Dividers

Status: **APPROVED CURRENT BASELINE**

```css
:root {
  --ci-border-width: 1px;
  --ci-divider-width: 1px;
}
```

Light Mode:

```css
border: 1px solid #E7E3DE;
```

Dark Mode:

```css
border: 1px solid #434A4D;
```

Rules:

- Avoid heavy 2px borders around every component.
- Use subtle borders to define structure.
- Reserve 2px borders for active or selected states only.
- Dividers should be used sparingly.
- Do not combine a strong border with a strong shadow on the same component.

Upload Drop-Zone Border:

```css
border: 1px dashed #9DBBB7;
```

Dark Mode:

```css
border: 1px dashed #52726E;
```

The dashed border indicates an upload/drop area. It must not resemble an error state.

---

## 8. Shadows and Elevation

Status: **APPROVED CURRENT BASELINE**

```css
:root {
  --ci-shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --ci-shadow-md: 0 4px 16px rgba(0, 0, 0, 0.08);
}
```

Usage:

- Standard cards: no shadow or `--ci-shadow-sm`
- Privacy disclosure: no shadow or `--ci-shadow-sm`
- Modal/dialog/major overlay only: `--ci-shadow-md`
- Do not use heavy decorative shadows.
- Dark Mode should rely mainly on surface contrast and borders, not glowing shadows.

---

## 9. Primary Button

Status: **APPROVED CURRENT BASELINE**

Dimensions:

```css
:root {
  --ci-button-height: 56px;
  --ci-button-padding-x: 24px;
  --ci-button-radius: 12px;
  --ci-button-icon-size: 22px;
  --ci-button-icon-gap: 10px;
}
```

Light Mode:

```css
.ci-button-primary {
  min-height: 56px;
  width: 100%;
  padding: 0 24px;
  border: 1px solid #0F766E;
  border-radius: 12px;
  background: #0F766E;
  color: #FFFFFF;
  font-size: 17px;
  line-height: 24px;
  font-weight: 600;
}
```

Hover-capable devices:

```css
.ci-button-primary:hover {
  background: #13867D;
  border-color: #13867D;
}
```

Pressed:

```css
.ci-button-primary:active {
  transform: translateY(1px);
  background: #0C665F;
}
```

Dark Mode:

```css
.ci-button-primary {
  background: #2F928A;
  border-color: #2F928A;
  color: #FFFFFF;
}
```

Dark Mode hover:

```css
.ci-button-primary:hover {
  background: #3AA49B;
  border-color: #3AA49B;
}
```

Disabled:

```css
.ci-button-primary:disabled {
  background: #C9CFCD;
  border-color: #C9CFCD;
  color: #707574;
  cursor: not-allowed;
  transform: none;
}
```

Dark Mode disabled:

```css
.ci-button-primary:disabled {
  background: #3B4444;
  border-color: #3B4444;
  color: #858D8C;
}
```

Rules:

- Do not use bright red for the upload button.
- Button text and icon must remain centred.
- Touch target must be at least 44px; the proposed standard is 56px.
- Do not use unnecessary gradients in the first implementation.
- Do not animate the button continuously.
- Loading state may replace the upload icon with a spinner, while preserving button dimensions.

---

## 10. Secondary and Tertiary Buttons

Status: **APPROVED CURRENT BASELINE**

Secondary Button:

```css
.ci-button-secondary {
  min-height: 52px;
  padding: 0 20px;
  border: 1px solid #0F766E;
  border-radius: 12px;
  background: transparent;
  color: #0F766E;
  font-size: 16px;
  line-height: 24px;
  font-weight: 600;
}
```

Tertiary Text Button:

```css
.ci-button-tertiary {
  min-height: 44px;
  padding: 8px 4px;
  border: 0;
  background: transparent;
  color: #0F766E;
  font-size: 16px;
  line-height: 24px;
  font-weight: 500;
}
```

Do not present secondary and tertiary buttons with the same visual weight as the primary upload action.

The uploader's Replace and Remove actions use the same Secondary Button treatment. Removing a selected image is a reversible workflow action, not a destructive action.

Selected Streamlit radio controls must use Primary Teal through the supported Streamlit theme configuration:

```toml
[theme]
primaryColor = "#0F766E"
```

Do not target generated Streamlit or BaseWeb radio markup with private-DOM CSS.

---

## 11. Cards

Status: **APPROVED CURRENT BASELINE**

Standard Card:

```css
.ci-card {
  background: #FFFFFF;
  border: 1px solid #E7E3DE;
  border-radius: 16px;
  padding: 24px 20px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}
```

Dark Mode:

```css
.ci-card {
  background: #202426;
  border-color: #434A4D;
  box-shadow: none;
}
```

Rules:

- Use cards only when they group related information or controls.
- Do not place every text block inside a separate card.
- Avoid nested cards unless functionally necessary.
- Cards must not visually compete with the primary action.

---

## 12. Upload Area

Status: **APPROVED CURRENT BASELINE**

The upload area is the main action on the current home screen.

Structure:

1. Upload-area heading
2. Primary upload button
3. Optional error/status message when validation feedback is required

Proposed CSS:

```css
.ci-upload-area {
  width: 100%;
  padding: 24px 20px;
  border: 1px dashed #9DBBB7;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.58);
  text-align: center;
}
```

Dark Mode:

```css
.ci-upload-area {
  border-color: #52726E;
  background: rgba(32, 36, 38, 0.72);
}
```

Upload heading:

```css
.ci-upload-title {
  margin: 0 0 20px;
  color: #1E1E20;
  font-size: 18px;
  line-height: 26px;
  font-weight: 600;
}
```

Do not permanently display supported formats or the upload limit on the upload surface. Show localized validation feedback only when a selected file cannot be used.

---

## 13. Privacy / Storage Disclosure

Status: **APPROVED CURRENT BASELINE**

The privacy/storage control is secondary information and must not compete with the upload action.

```css
.ci-disclosure {
  width: 100%;
  min-height: 56px;
  padding: 14px 16px;
  border: 1px solid #E7E3DE;
  border-radius: 12px;
  background: #FFFFFF;
  color: #1E1E20;
}
```

Dark Mode:

```css
.ci-disclosure {
  border-color: #434A4D;
  background: #202426;
  color: #F4F3F1;
}
```

Disclosure title:

```css
font-size: 16px;
line-height: 24px;
font-weight: 500;
```

Disclosure body:

```css
padding-top: 12px;
padding-bottom: 16px;
font-size: 14px;
line-height: 21px;
font-weight: 400;
```

Rules:

- Use a consistent chevron icon.
- Expanded/collapsed state must be visually clear.
- The full row must be clickable.
- Minimum touch target: 44px.
- Do not use a heavy shadow.
- Expanded content must preserve balanced 16px top and bottom internal spacing; nested Markdown margins must not consume the bottom padding.

---

## 14. Icon Style

Status: **PROPOSED — PENDING VISUAL VALIDATION**

- Use outline icons.
- Nominal stroke width: 2px.
- Rounded line caps and joins.
- Standard interface icon size: 20–24px.
- Button icon size: 22px.
- Icons must come from one consistent icon system.
- Do not mix emoji, Unicode symbols, Streamlit icons, filled icons, and unrelated icon libraries.
- Do not use the current yarn emoji as the permanent product logo.
- Destructive icons may use the error colour.
- Standard functional icons use the current text or primary colour.

Required initial icons:

- upload
- image
- camera, if camera capture remains supported
- replace/change image
- remove/delete
- information
- privacy/security
- download
- chevron-right
- chevron-down

---

## 15. Responsive Layout

Status: **APPROVED CURRENT BASELINE**

Mobile First:

```css
.ci-page {
  width: 100%;
  max-width: 720px;
  margin: 0 auto;
  padding-left: 20px;
  padding-right: 20px;
}
```

Small phones below 360px:

```css
@media (max-width: 359px) {
  .ci-page {
    padding-left: 16px;
    padding-right: 16px;
  }
}
```

Tablet and desktop:

```css
@media (min-width: 768px) {
  .ci-page {
    padding-left: 32px;
    padding-right: 32px;
  }
}
```

Rules:

- Do not simply enlarge all mobile elements on desktop.
- Preserve a readable maximum content width.
- Primary actions remain easily reachable and obvious.
- Do not use multi-column layouts on the initial upload screen unless later content requires them.

---

## 16. Touch and Accessibility

Status: **REQUIRED**

- Minimum interactive touch target: 44px × 44px.
- Preferred primary-action height: 56px.
- Do not rely on colour alone to indicate error, success, selected, or disabled states.
- All interactive elements require visible focus styles.
- All icons that convey meaning require accessible labels.
- Decorative icons must be hidden from assistive technology.
- Text must remain readable at browser zoom.
- Avoid fixed-height text containers that clip translated content.
- Allow Chinese, Japanese, and English labels to wrap when necessary.
- Do not truncate important action labels.
- Respect `prefers-reduced-motion`.
- Respect `prefers-color-scheme`.

---

## 17. Current Home-Screen Content Rules

Status: **CURRENT DIRECTION**

The first implementation should contain only the necessary workflow elements:

- product title
- product subtitle
- upload area
- upload button
- privacy/storage disclosure

Do not add decorative yarn, hook, leaf, or floral graphics to empty space in the application screen.

Reason:

The empty area may later be used for functional GIF/JPEG guidance explaining:

- which crochet patterns can be translated
- which crochet patterns cannot be translated
- how users should photograph or upload patterns

Future guidance media must be treated as instructional product content, not decoration.

---

## 18. Interface Language Selector

Status: **PLANNED REMOVAL FROM APPLICATION**

Current state:

- The interface-language selector remains inside the application during the current transition.

Future state:

- Remove it from the application after the Crochet Intelligence Landing Page provides platform-level language selection.

Do not redesign or heavily invest in the current in-app selector unless required for temporary usability.

---

## 19. Streamlit Technical Issue

Status: **RESOLVED FOR CURRENT BASELINE**

Issue:

- The Streamlit three-dot menu at the top-right of the application is visually intrusive.
- It exposes the underlying framework and weakens product branding.

Current implementation:

- Use supported Streamlit configuration `client.toolbarMode = "minimal"`.
- Do not hide the menu with private-DOM CSS.
- The RC51 Home Screen baseline passed physical-iPhone Human Visual UAT with this configuration.

---

## 20. Validation Requirements

After implementation, perform visual review on at least:

- iPhone Light Mode
- iPhone Dark Mode
- Android Light Mode
- Android Dark Mode
- desktop browser

Review:

- title size
- subtitle size
- button height
- page padding
- card width
- upload-area padding
- colour temperature
- text contrast
- border visibility
- Dark Mode surface separation
- translated-text wrapping

Any approved value that later looks too large, too small, too warm, too cold, too heavy, or too weak may be replaced after Human Visual UAT and explicit Product Owner approval.

The approved current baseline is not a final UI freeze.

---

## 21. Update Rule

This file must always describe the UI values that the programmer should implement now.

When a value changes after visual validation:

1. replace the old value
2. update the corresponding CSS variable or specification
3. update the matching PNG Reference Card
4. verify Light Mode and Dark Mode again
5. do not retain rejected values in the active specification

End of specification.
