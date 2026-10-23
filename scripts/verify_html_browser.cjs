// Optional local verifier. No Node package is required by TraceBench itself.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const directory = process.argv[2];
const { chromium } = require(process.argv[3]);
const expected = JSON.parse(fs.readFileSync(path.join(directory, 'expected.json'), 'utf8'));
const url = name => pathToFileURL(path.join(directory, name)).href;

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    page.setDefaultTimeout(5000);
    const network = [], errors = [];
    page.on('request', request => { if (/^https?:/.test(request.url())) network.push(request.url()); });
    page.on('pageerror', error => errors.push(String(error)));
    await page.goto(url('hostile.html'));
    assert.equal(await page.locator('#controls').isVisible(), true, 'CSP must allow only the fixed UI script');
    assert.equal(await page.locator('article').count(), 5);
    assert.equal(await page.locator('img,svg,iframe,a,form').count(), 0, 'recorded text must not create elements');
    assert.equal(await page.evaluate(() => globalThis.pwned), undefined);
    const hostileCard = page.locator('article').last();
    assert.equal(await hostileCard.locator('.case-id').textContent(), expected.hostile_id);
    assert.equal(JSON.parse(await hostileCard.locator('.output').textContent()), expected.hostile, 'full output must survive HTML parsing exactly');
    for (const [filter, count] of [['all', 5], ['passed', 2], ['failed', 3], ['regressions', 1], ['improvements', 1]]) {
      await page.getByLabel('Case status', { exact: true }).selectOption(filter);
      assert.equal(await page.locator('article:visible').count(), count, filter);
      assert.equal(await page.getByRole('status').textContent(), `${count} / 5 cases visible`);
    }
    await page.getByLabel('Case status', { exact: true }).selectOption('all');
    const search = page.getByLabel('Search case ID or recorded output');
    await search.fill('IMPROVED');
    assert.equal(await page.locator('article:visible .case-id').textContent(), 'improved');
    await search.fill('你好');
    assert.equal(await page.locator('article:visible').count(), 1, 'search includes full recorded output');
    await search.fill('</script>');
    assert.equal(await page.locator('article:visible').count(), 1, 'search includes literal output text, not just JSON escapes');
    await search.fill('<b>structured');
    assert.equal(await page.locator('article:visible .case-id').textContent(), 'stable-pass');
    await search.fill('9007199254740993');
    assert.equal(await page.locator('article:visible').count(), 1, 'search retains exact large decimals');
    await search.fill('9007199254740992');
    assert.equal(await page.locator('article:visible').count(), 0, 'search must not invent rounded numeric content');
    await search.fill('unfindable');
    assert.equal(await page.locator('article:visible').count(), 0);
    assert.equal(await page.getByRole('status').textContent(), '0 / 5 cases visible');
    await search.fill('');
    await search.focus();
    await page.keyboard.press('Tab');
    assert.equal(await page.locator('#case-filter').evaluate(node => node === document.activeElement), true);
    await page.keyboard.press('p');
    await page.keyboard.press('Tab');
    assert.equal(await page.locator('#case-filter').inputValue(), 'passed');
    assert.equal(await page.locator('article:visible').count(), 2, 'keyboard changes filters');
    await page.getByLabel('Case status', { exact: true }).selectOption('all');
    const summary = page.locator('article').first().locator('summary').first();
    await summary.focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('article').first().locator('details').first().getAttribute('open'), '');
    await page.goto(url('sample.html'));
    for (const [name, width] of [['desktop', 1280], ['mobile', 390], ['small-mobile', 320]]) {
      await page.setViewportSize({ width, height: 900 });
      await page.locator('details').evaluateAll(nodes => nodes.forEach(node => node.open = true));
      const sizes = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, view: innerWidth }));
      assert.ok(sizes.scroll <= sizes.view, `horizontal overflow at ${width}px: ${JSON.stringify(sizes)}`);
      if (name !== 'small-mobile') await page.screenshot({ path: path.join(directory, `${name}.png`), fullPage: true });
    }
    await page.getByLabel('Search case ID or recorded output').fill('no match');
    await page.locator('details').evaluateAll(nodes => nodes.forEach(node => node.open = false));
    await page.emulateMedia({ media: 'print' });
    assert.equal(await page.locator('#controls').isVisible(), false);
    assert.equal(await page.locator('article:visible').count(), 6, 'print includes filtered-out cases');
    for (const content of await page.locator('.output,.reason').all()) {
      assert.equal(await content.isVisible(), true, 'print expands full output and check reasons');
    }
    await page.pdf({ path: path.join(directory, 'print.pdf'), format: 'A4', printBackground: true });
    const noJS = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 900 } });
    const plain = await noJS.newPage();
    plain.on('request', request => { if (/^https?:/.test(request.url())) network.push(request.url()); });
    await plain.goto(url('hostile.html'));
    assert.equal(await plain.locator('article:visible').count(), 5);
    assert.equal(await plain.locator('#controls').isVisible(), false);
    await plain.locator('summary').first().click();
    assert.equal(await plain.locator('.output').first().isVisible(), true, 'native details works without JavaScript');
    await plain.emulateMedia({ media: 'print' });
    for (const content of await plain.locator('.output,.reason').all()) {
      assert.equal(await content.isVisible(), true, 'print expands all details without JavaScript');
    }
    await plain.emulateMedia({ media: 'screen' });
    await page.emulateMedia({ media: 'screen' });
    await page.goto(url('hostile.html'));
    await page.locator('details').evaluateAll(nodes => nodes.forEach(node => node.open = true));
    for (const width of [1280, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `long hostile output wraps at ${width}px`);
    }
    assert.equal(await plain.locator('img,svg').count(), 0);
    assert.deepEqual(errors, []);
    assert.deepEqual(network, [], 'report makes no HTTP(S) requests');
    console.log(`Chromium ${browser.version()}: desktop/mobile 1280/390/320px, full text, search, all filters, keyboard, no-JS, print, hostile markup and zero network requests verified.`);
    await noJS.close();
    await context.close();
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
