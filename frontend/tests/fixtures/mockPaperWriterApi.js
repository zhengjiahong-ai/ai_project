/**
 * Mock /api/generate-paper-draft endpoint for E2E tests.
 */
export function installMockPaperWriterApi(page) {
  return page.route('**/generate-paper-draft', async (route) => {
    const body = route.request().postDataJSON() || {};
    const question = body.question || 'default question';
    const title = body.title || `A Review of ${question.slice(0, 40)}`;

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'done',
        title,
        question,
        sections: [
          { heading: 'Abstract', wordCount: 120, body: 'This paper reviews ' + question + '. Key findings are summarized.' },
          { heading: 'Introduction', wordCount: 200, body: '## Introduction\n\nThe field of ' + question + ' has seen rapid progress.' },
          { heading: 'Related Work', wordCount: 180, body: '## Related Work\n\nPrior work has explored various aspects.' },
          { heading: 'Methodology', wordCount: 150, body: '## Methodology\n\nWe employ a systematic review approach.' },
          { heading: 'Results', wordCount: 250, body: '## Results\n\nAnalysis reveals several key findings.\n\n- Finding 1: Evidence supports the main claim.\n- Finding 2: Cross-paper consistency is moderate.' },
          { heading: 'Discussion', wordCount: 160, body: '## Discussion\n\nThe results suggest promising directions.' },
          { heading: 'Conclusion', wordCount: 100, body: '## Conclusion\n\nThis review identified key patterns.' },
        ],
        referenceCount: 8,
        markdown: '# ' + title + '\n\nGenerated paper draft.',
        latex: '\\documentclass{article}\n\\begin{document}\n' + title + '\n\\end{document}',
        bibtex: '@article{test,\n  author = {Author},\n  title = {' + title + '},\n  year = {2024}\n}',
        sty: '% Pixiu Paper Draft Style File\n\\ProvidesPackage{pixiu-paper}',
        outputFiles: {
          markdown: 'paper.md',
          latex: 'paper.tex',
          bibtex: 'references.bib',
          sty: 'pixiu-paper.sty',
        },
      }),
    });
  });
}
