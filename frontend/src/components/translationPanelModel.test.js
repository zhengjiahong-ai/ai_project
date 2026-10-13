import assert from 'node:assert/strict';

import { createTranslationPanelViewModel } from './translationPanelModel.js';

const singleColumnLayout = {
  viewport: { width: 600, height: 800 },
  orientation: 'portrait',
  columnMode: 'single-column',
  blocks: [
    {
      id: 'block-1',
      text: 'Source paragraph',
      bbox: { left: 0.08, top: 0.16, width: 0.4, height: 0.08 },
      style: { fontSize: 12, fontWeight: 'normal', italic: false },
      readingOrder: 0,
    },
  ],
};

const run = () => {
  const plainTranslation = createTranslationPanelViewModel({
    status: 'success',
    renderMode: 'plain',
    translatedText: '这是图题的译文。',
    translatedBlocks: [],
    pageLayout: singleColumnLayout,
  });
  assert.equal(plainTranslation.canRenderFidelity, false);
  assert.equal(plainTranslation.canRenderStructuredFallback, false);
  assert.equal(plainTranslation.shouldShowPlainTranslation, true);

  const imageOnlyLegacyPage = createTranslationPanelViewModel({
    status: 'empty',
    renderMode: 'overlay',
    translatedText: '',
    translatedBlocks: [],
    figureSnippets: [
      {
        id: 'figure-1',
        type: 'figure',
        bbox: { left: 0.5, top: 0.34, width: 0.3, height: 0.22 },
        image: 'data:image/png;base64,figure',
      },
    ],
    pageLayout: singleColumnLayout,
  });
  assert.equal(imageOnlyLegacyPage.canRenderFidelity, false);
  assert.equal(imageOnlyLegacyPage.canRenderStructuredFallback, false);
  assert.equal(imageOnlyLegacyPage.shouldShowPlainTranslation, false);

  const structuredOverlay = createTranslationPanelViewModel({
    status: 'success',
    renderMode: 'overlay',
    translatedText: '这是正文译文。',
    translatedBlocks: [{ id: 'block-1', translatedText: '这是正文译文。' }],
    pageLayout: singleColumnLayout,
  });
  assert.equal(structuredOverlay.canRenderFidelity, true);
  assert.equal(structuredOverlay.panoramicText, '这是正文译文。');
  const cachedFormula = createTranslationPanelViewModel({translatedBlocks:[
    {id:'block-1',translatedText:'正文译文'}, {id:'formula',translatedText:'损坏的公式碎片'}],
    pageLayout:{...singleColumnLayout,blocks:[...singleColumnLayout.blocks,{id:'formula',text:'C = x + y, (2)',
      bbox:{left:0.3,top:0.5,width:0.3,height:0.03}}]}});
  assert.equal(cachedFormula.panoramicText, '正文译文');
  assert.equal(cachedFormula.panoramicArtifactText, '正文译文');
  const unmatched = createTranslationPanelViewModel({translatedText:'已有全文译文',
    translatedBlocks:[{id:'old-id',translatedText:'已有全文译文'}],pageLayout:singleColumnLayout});
  assert.equal(unmatched.panoramicArtifactText,'已有全文译文');
  const formulaOnly = createTranslationPanelViewModel({translatedText:'损坏公式',
    translatedBlocks:[{id:'formula',translatedText:'损坏公式'}],pageLayout:{...singleColumnLayout,
      blocks:[{id:'formula',text:'C = x + y, (2)',bbox:{left:0.3,top:0.5,width:0.3,height:0.03}}]}});
  assert.equal(formulaOnly.panoramicArtifactText,'');
  const mathLayout = {...singleColumnLayout,blocks:[{...singleColumnLayout.blocks[0],text:'The volume is V(Σj) = 43πabc.'}]};
  const legacyMath = createTranslationPanelViewModel({translatedText:'体积是43πabc。',
    translatedBlocks:[{id:'block-1',translatedText:'体积是43πabc。'}],pageLayout:mathLayout});
  assert.equal(legacyMath.mathNotice,'旧译文未保护行内公式，请以原图为准。');
  assert.ok(legacyMath.panoramicArtifactText.startsWith('> 旧译文未保护行内公式'));
  assert.ok(legacyMath.panoramicArtifactText.includes('体积是43πabc。'));
  const protectedMath = createTranslationPanelViewModel({translatedText:'体积为⟦原式1⟧。',mathProtectionVersion:1,
    translatedBlocks:[{id:'block-1',translatedText:'体积为⟦原式1⟧。'}],pageLayout:mathLayout});
  assert.ok(protectedMath.mathNotice.includes('原式标记'));
  assert.ok(protectedMath.panoramicArtifactText.includes('⟦原式1⟧'));

  const plainWithExcludedZones = createTranslationPanelViewModel({
    status: 'success',
    renderMode: 'plain',
    translatedText: '这是图文混排页面的译文。',
    translatedBlocks: [],
    backgroundImage: 'data:image/png;base64,page',
    excludedZones: [{ type: 'figure', bbox: { left: 0.5, top: 0.34, width: 0.3, height: 0.22 } }],
    pageLayout: singleColumnLayout,
  });
  assert.equal(plainWithExcludedZones.shouldShowPlainTranslation, true);

  console.log('frontend translation panel model tests passed');
};

run();
